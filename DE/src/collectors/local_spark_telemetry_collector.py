"""Local Spark telemetry collector (JSON/CSV fixtures for development)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.rca.evidence_pack import build_evidence_pack
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _load_records(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        logger.warning("local_spark_telemetry_path_missing", path=path)
        return []
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return [r for r in data["records"] if isinstance(r, dict)]
        return []
    # CSV
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _match_run(
    rows: List[Dict[str, Any]],
    *,
    job_run_id: str,
    job_run_date: Optional[str] = None,
    task_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        if str(r.get("job_run_id") or "") != str(job_run_id):
            continue
        if job_run_date and str(r.get("job_run_date") or "") != str(job_run_date):
            continue
        if task_key and str(r.get("task_key") or "") != str(task_key):
            continue
        out.append(r)
    return out


class LocalSparkTelemetryCollector:
    """Load spark_logs / spark_metrics from local JSON or CSV files."""

    def __init__(
        self,
        *,
        spark_logs_path: Optional[str] = None,
        spark_metrics_path: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        cfg = settings or default_settings
        self._logs = _load_records(spark_logs_path or cfg.local_spark_logs_path)
        self._metrics = _load_records(spark_metrics_path or cfg.local_spark_metrics_path)

    def get_failure_anchors(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = _match_run(
            self._metrics, job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
        )
        out = []
        for r in rows:
            et = (r.get("event_type") or "").strip()
            if et not in ("pipeline_end", "spark_sql_query_error"):
                continue
            successful = r.get("successful")
            status = str(r.get("status") or "").lower()
            if (
                successful is False
                or successful == "false"
                or status
                in (
                    "failure",
                    "failed",
                    "error",
                )
            ):
                out.append(r)
            elif et == "spark_sql_query_error":
                out.append(r)
        return out

    def get_stage_pressure(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = _match_run(
            self._metrics, job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
        )
        types = {"spark_job_completed", "spark_stage_completed", "spark_stage_task_summary"}
        return [r for r in rows if (r.get("event_type") or "") in types][:40]

    def get_error_logs(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = _match_run(
            self._logs, job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
        )
        out = []
        for r in rows:
            level = str(r.get("log_level") or "").upper()
            if level in ("ERROR", "WARNING") or r.get("exception"):
                out.append(r)
        return out[:100]

    def get_timeline(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        rows = _match_run(
            self._metrics, job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
        )
        allowed = {
            "pipeline_start",
            "pipeline_end",
            "spark_sql_query_observed",
            "spark_sql_query_error",
            "spark_job_start",
            "spark_job_completed",
            "spark_stage_start",
            "spark_stage_completed",
        }
        filtered = [r for r in rows if (r.get("event_type") or "") in allowed]
        return sorted(filtered, key=lambda r: str(r.get("event_ts") or ""))[:80]

    def list_failed_runs(
        self,
        *,
        job_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        by_key: Dict[str, Dict[str, Any]] = {}
        for r in self._metrics:
            if str(r.get("job_id") or "") != str(job_id):
                continue
            et = (r.get("event_type") or "").strip()
            successful = r.get("successful")
            status = str(r.get("status") or "").lower()
            is_fail = et == "spark_sql_query_error" or (
                et == "pipeline_end"
                and (
                    successful is False
                    or successful == "false"
                    or status in ("failure", "failed", "error")
                )
            )
            if not is_fail:
                continue
            jrd = str(r.get("job_run_date") or "")
            if start_date and jrd and jrd < start_date:
                continue
            if end_date and jrd and jrd > end_date:
                continue
            key = f"{r.get('job_run_id')}|{r.get('task_key') or ''}"
            prev = by_key.get(key)
            ts = str(r.get("event_ts") or "")
            if not prev or ts > str(prev.get("last_event_ts") or ""):
                by_key[key] = {
                    "job_id": r.get("job_id"),
                    "job_run_id": r.get("job_run_id"),
                    "job_run_date": r.get("job_run_date"),
                    "task_key": r.get("task_key"),
                    "job_name": r.get("job_name"),
                    "pipeline": r.get("pipeline"),
                    "workspace_id": r.get("workspace_id"),
                    "workspace_name": r.get("workspace_name"),
                    "last_event_ts": ts,
                    "failure_reason": r.get("failure_reason"),
                    "failure_event_count": (
                        (prev or {}).get("failure_event_count", 0) + 1 if prev else 1
                    ),
                }
            elif prev:
                prev["failure_event_count"] = int(prev.get("failure_event_count") or 0) + 1
        rows = sorted(
            by_key.values(), key=lambda x: str(x.get("last_event_ts") or ""), reverse=True
        )
        return rows[:limit]

    def build_evidence_pack_for_run(
        self,
        *,
        job_run_id: str,
        job_id: Optional[str] = None,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        anchors = self.get_failure_anchors(
            job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
        )
        if not job_run_date and anchors:
            job_run_date = anchors[0].get("job_run_date")
        if not job_id and anchors:
            job_id = anchors[0].get("job_id")
        return build_evidence_pack(
            job_run_id=job_run_id,
            job_id=job_id,
            job_run_date=job_run_date,
            task_key=task_key,
            workspace_id=workspace_id,
            failure_anchors=anchors,
            stage_pressure=self.get_stage_pressure(
                job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
            ),
            error_logs=self.get_error_logs(
                job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
            ),
            timeline=self.get_timeline(
                job_run_id=job_run_id, job_run_date=job_run_date, task_key=task_key
            ),
        )
