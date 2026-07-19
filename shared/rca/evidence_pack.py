"""Bounded evidence pack builder for Spark job failure RCA."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def _parse_attributes(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"raw": raw}
        except json.JSONDecodeError:
            return {"raw": raw}
    return {"raw": str(raw)}


def _truncate(text: Optional[str], max_len: int = 800) -> str:
    if not text:
        return ""
    s = str(text).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _event_ref(event: Dict[str, Any], prefix: str = "metrics") -> str:
    eid = event.get("event_id") or event.get("log_timestamp") or "unknown"
    et = event.get("event_type") or event.get("log_level") or "event"
    return f"{prefix}:{et}:{eid}"


def build_evidence_pack(
    *,
    job_run_id: str,
    job_id: Optional[str] = None,
    job_run_date: Optional[str] = None,
    task_key: Optional[str] = None,
    workspace_id: Optional[str] = None,
    failure_anchors: Optional[List[Dict[str, Any]]] = None,
    stage_pressure: Optional[List[Dict[str, Any]]] = None,
    error_logs: Optional[List[Dict[str, Any]]] = None,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Normalize collector rows into a stable evidence pack for the LLM."""
    anchors = failure_anchors or []
    stages = stage_pressure or []
    logs = error_logs or []
    events = timeline or []

    pipeline_end: Optional[Dict[str, Any]] = None
    sql_errors: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []

    for row in anchors:
        attrs = _parse_attributes(row.get("attributes"))
        et = (row.get("event_type") or "").strip()
        item = {
            "event_id": row.get("event_id"),
            "event_type": et,
            "event_ts": row.get("event_ts"),
            "task_key": row.get("task_key"),
            "status": row.get("status"),
            "successful": row.get("successful"),
            "failure_reason": row.get("failure_reason"),
            "attributes": attrs,
        }
        ref = _event_ref(row, "metrics")
        excerpt_parts = [
            row.get("failure_reason"),
            attrs.get("error_type"),
            attrs.get("error_message"),
            attrs.get("sql_text"),
        ]
        evidence.append(
            {
                "source": "spark_metrics",
                "ref": ref,
                "excerpt": _truncate(" | ".join(str(p) for p in excerpt_parts if p)),
            }
        )
        if et == "pipeline_end":
            pipeline_end = item
        elif et == "spark_sql_query_error":
            sql_errors.append(item)

    for row in stages[:20]:
        attrs = _parse_attributes(row.get("attributes"))
        ref = _event_ref(row, "metrics")
        summary = (
            f"{row.get('event_type')} status={attrs.get('status') or row.get('status')} "
            f"failed_tasks={attrs.get('num_failed_tasks')} "
            f"shuffle_read={attrs.get('shuffle_read_bytes')} "
            f"shuffle_write={attrs.get('shuffle_write_bytes')}"
        )
        evidence.append(
            {
                "source": "spark_metrics",
                "ref": ref,
                "excerpt": _truncate(summary),
            }
        )

    top_exceptions: List[Dict[str, Any]] = []
    for row in logs[:100]:
        ref = _event_ref(
            {
                "event_id": row.get("log_timestamp"),
                "event_type": row.get("log_level"),
                "log_timestamp": row.get("log_timestamp"),
                "log_level": row.get("log_level"),
            },
            "logs",
        )
        exc = row.get("exception")
        msg = row.get("message")
        evidence.append(
            {
                "source": "spark_logs",
                "ref": ref,
                "excerpt": _truncate(exc or msg),
            }
        )
        if exc:
            top_exceptions.append(
                {
                    "log_timestamp": row.get("log_timestamp"),
                    "logger_name": row.get("logger_name"),
                    "message": _truncate(msg, 400),
                    "exception": _truncate(exc, 2000),
                    "task_key": row.get("task_key"),
                }
            )

    timeline_out: List[Dict[str, Any]] = []
    for row in events[:40]:
        attrs = _parse_attributes(row.get("attributes"))
        summary = row.get("failure_reason") or attrs.get("error_message") or attrs.get("status")
        if not summary:
            summary = row.get("event_type") or ""
        timeline_out.append(
            {
                "ts": row.get("event_ts"),
                "event_type": row.get("event_type"),
                "summary": _truncate(str(summary), 240),
                "task_key": row.get("task_key"),
                "status": row.get("status"),
            }
        )

    return {
        "job_run_id": job_run_id,
        "job_id": job_id,
        "job_run_date": job_run_date,
        "task_key": task_key,
        "workspace_id": workspace_id,
        "raw_anchors": {
            "pipeline_end": pipeline_end,
            "sql_errors": sql_errors,
            "top_exceptions": top_exceptions[:10],
            "stage_pressure_count": len(stages),
        },
        "timeline": timeline_out,
        "evidence": evidence[:80],
    }
