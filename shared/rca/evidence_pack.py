"""Bounded evidence pack builder for Spark job failure RCA."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Protocol

# Plan / SQL fields kept longer so STEP 3 skills can fire.
_PLAN_ATTR_KEYS = (
    "sql_text",
    "physical_plan",
    "logical_plan",
    "join_types",
    "error_type",
    "error_message",
    "shuffle_operations",
    "aggregation_patterns",
)
_SQL_EVENT_TYPES = frozenset({"spark_sql_query_error", "spark_sql_query_observed"})
_LONG_PLAN_KEYS = frozenset({"physical_plan", "logical_plan", "sql_text"})


class _TelemetryCollector(Protocol):
    def get_failure_anchors(self, *, job_run_id: str, job_run_date=None, task_key=None): ...
    def get_stage_pressure(self, *, job_run_id: str, job_run_date=None, task_key=None): ...
    def get_error_logs(self, *, job_run_id: str, job_run_date=None, task_key=None): ...
    def get_timeline(self, *, job_run_id: str, job_run_date=None, task_key=None): ...
    def get_sql_plans(self, *, job_run_id: str, job_run_date=None, task_key=None): ...


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


def _metric_item(row: Dict[str, Any], attrs: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "event_id": row.get("event_id"),
        "event_type": (row.get("event_type") or "").strip(),
        "event_ts": row.get("event_ts"),
        "task_key": row.get("task_key"),
        "status": row.get("status"),
        "successful": row.get("successful"),
        "failure_reason": row.get("failure_reason"),
        "attributes": attrs,
    }


def _plan_attrs(row: Dict[str, Any]) -> Dict[str, Any]:
    attrs = _parse_attributes(row.get("attributes"))
    for key in _PLAN_ATTR_KEYS:
        if attrs.get(key) in (None, "") and row.get(key) not in (None, ""):
            attrs[key] = row.get(key)
    out: Dict[str, Any] = {}
    for k, v in attrs.items():
        if k not in _PLAN_ATTR_KEYS and k != "sql_execution_id":
            continue
        if k in _LONG_PLAN_KEYS and not isinstance(v, (dict, list)):
            out[k] = _truncate(str(v), 2000)
        else:
            out[k] = v
    return out


def _plan_excerpt(attrs: Dict[str, Any], failure_reason: Any = None) -> str:
    parts: List[str] = []
    if failure_reason:
        parts.append(str(failure_reason))
    for key in _PLAN_ATTR_KEYS:
        val = attrs.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, (dict, list)):
            val = json.dumps(val, default=str)
        max_len = 2000 if key in _LONG_PLAN_KEYS else 400
        parts.append(f"{key}={_truncate(str(val), max_len)}")
    return _truncate(" | ".join(parts), 4000)


def assemble_evidence_pack_for_run(
    collector: _TelemetryCollector,
    *,
    job_run_id: str,
    job_id: Optional[str] = None,
    job_run_date: Optional[str] = None,
    task_key: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Shared assembly: section getters → one evidence pack (used by both collectors)."""
    kw = {"job_run_id": job_run_id, "job_run_date": job_run_date, "task_key": task_key}
    anchors = collector.get_failure_anchors(**kw)
    plans = collector.get_sql_plans(**kw)
    seed = (anchors or plans or [{}])[0]
    return build_evidence_pack(
        job_run_id=job_run_id,
        job_id=job_id or seed.get("job_id"),
        job_run_date=job_run_date or seed.get("job_run_date"),
        task_key=task_key,
        workspace_id=workspace_id,
        failure_anchors=anchors,
        stage_pressure=collector.get_stage_pressure(**kw),
        error_logs=collector.get_error_logs(**kw),
        timeline=collector.get_timeline(**kw),
        sql_plans=plans,
    )


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
    sql_plans: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Normalize collector rows into a stable evidence pack for the LLM."""
    anchors = list(failure_anchors or [])
    stages = stage_pressure or []
    logs = error_logs or []
    events = timeline or []
    plans = list(sql_plans or [])

    # Backward compatible: SQL events may still arrive via failure_anchors.
    if not plans:
        plans = [r for r in anchors if (r.get("event_type") or "").strip() in _SQL_EVENT_TYPES]
        anchors = [
            r for r in anchors if (r.get("event_type") or "").strip() not in _SQL_EVENT_TYPES
        ]

    pipeline_end: Optional[Dict[str, Any]] = None
    sql_errors: List[Dict[str, Any]] = []
    sql_observed: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    stage_excerpts: List[Dict[str, Any]] = []

    for row in anchors:
        attrs = _parse_attributes(row.get("attributes"))
        item = _metric_item(row, attrs)
        evidence.append(
            {
                "source": "spark_metrics",
                "ref": _event_ref(row),
                "excerpt": _truncate(
                    " | ".join(
                        str(p)
                        for p in (
                            row.get("failure_reason"),
                            attrs.get("error_type"),
                            attrs.get("error_message"),
                        )
                        if p
                    )
                ),
            }
        )
        if item["event_type"] == "pipeline_end":
            pipeline_end = item

    for row in plans[:30]:
        attrs = _plan_attrs(row)
        et = (row.get("event_type") or "").strip()
        item = _metric_item(row, attrs)
        evidence.append(
            {
                "source": "spark_metrics",
                "ref": _event_ref(row),
                "excerpt": _plan_excerpt(attrs, row.get("failure_reason")),
            }
        )
        if et == "spark_sql_query_error":
            sql_errors.append(item)
        elif et == "spark_sql_query_observed":
            sql_observed.append(item)

    for row in stages[:20]:
        attrs = _parse_attributes(row.get("attributes"))
        excerpt = _truncate(
            f"{row.get('event_type')} status={attrs.get('status') or row.get('status')} "
            f"failed_tasks={attrs.get('num_failed_tasks')} "
            f"shuffle_read={attrs.get('shuffle_read_bytes')} "
            f"shuffle_write={attrs.get('shuffle_write_bytes')} "
            f"memory_spill={attrs.get('memoryBytesSpilled') or attrs.get('memory_bytes_spilled')} "
            f"disk_spill={attrs.get('diskBytesSpilled') or attrs.get('disk_bytes_spilled')}"
        )
        item = {"source": "spark_metrics", "ref": _event_ref(row), "excerpt": excerpt}
        evidence.append(item)
        stage_excerpts.append(item)

    top_exceptions: List[Dict[str, Any]] = []
    for row in logs[:100]:
        exc = row.get("exception")
        msg = row.get("message")
        evidence.append(
            {
                "source": "spark_logs",
                "ref": _event_ref(
                    {
                        "event_id": row.get("log_timestamp"),
                        "event_type": row.get("log_level"),
                        "log_timestamp": row.get("log_timestamp"),
                        "log_level": row.get("log_level"),
                    },
                    "logs",
                ),
                "excerpt": _truncate(exc or msg, 2000),
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
        summary = (
            row.get("failure_reason")
            or attrs.get("error_message")
            or attrs.get("status")
            or row.get("event_type")
            or ""
        )
        timeline_out.append(
            {
                "ts": row.get("event_ts"),
                "event_type": row.get("event_type"),
                "summary": _truncate(str(summary), 240),
                "task_key": row.get("task_key"),
                "status": row.get("status"),
            }
        )

    sections = {
        "logs": {"top_exceptions": top_exceptions[:10]},
        "stage_metrics": {
            "pipeline_end": pipeline_end,
            "stage_pressure_excerpts": stage_excerpts,
            "timeline": timeline_out,
        },
        "sql_plans": {"sql_errors": sql_errors, "sql_observed": sql_observed[:10]},
    }

    return {
        "job_run_id": job_run_id,
        "job_id": job_id,
        "job_run_date": job_run_date,
        "task_key": task_key,
        "workspace_id": workspace_id,
        "sections": sections,
        # Kept for classify/validate/API compatibility (mirrors key section fields).
        "raw_anchors": {
            "pipeline_end": pipeline_end,
            "sql_errors": sql_errors,
            "sql_observed_count": len(sql_observed),
            "top_exceptions": top_exceptions[:10],
            "stage_pressure_count": len(stages),
        },
        "timeline": timeline_out,
        "evidence": evidence[:100],
    }
