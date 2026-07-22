"""Format evidence_pack slices for the RCA human prompt sections."""

from __future__ import annotations

import json
from typing import Any, Dict


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, indent=2)


def _section_text(section: Any, empty_message: str) -> str:
    if not section:
        return empty_message
    if isinstance(section, dict) and not any(section.values()):
        return empty_message
    return _dumps(section)


def format_rca_human_payload(
    evidence_pack: Dict[str, Any],
    *,
    classification_hint: str,
) -> Dict[str, str]:
    """Build ChatPromptTemplate variables for RCA_HUMAN_PROMPT."""
    sections = evidence_pack.get("sections") or {}

    def _s(value: Any) -> str:
        return "(not provided)" if value is None or value == "" else str(value)

    return {
        "workspace_id": _s(evidence_pack.get("workspace_id")),
        "job_id": _s(evidence_pack.get("job_id")),
        "job_run_id": _s(evidence_pack.get("job_run_id")),
        "job_run_date": _s(evidence_pack.get("job_run_date")),
        "task_key": _s(evidence_pack.get("task_key")),
        "classification_hint": classification_hint or "(none)",
        "cluster_logs_section": _section_text(
            sections.get("logs"),
            "(no ERROR/WARN/exception excerpts in this evidence_pack)",
        ),
        "spark_metrics_section": _section_text(
            sections.get("stage_metrics"),
            "(no stage/task metric excerpts in this evidence_pack)",
        ),
        "query_plans_section": _section_text(
            sections.get("sql_plans"),
            "(no sql_text/physical_plan/sql_error attrs in this evidence_pack)",
        ),
        "evidence_pack": _dumps(evidence_pack),
    }
