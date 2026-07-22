"""Validation rules for editable agent prompt templates."""

from __future__ import annotations

from typing import Dict, FrozenSet

from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID, SPARK_JOB_RCA_AGENT_ID

_CHAIN_PLACEHOLDER_KEYS: Dict[str, Dict[str, FrozenSet[str]]] = {
    DBX_CLUSTER_TUNING_AGENT_ID: {
        "sizing": frozenset(
            {
                "current_config",
                "job_run_ingest",
                "sizing_hints",
                "guardrail_feedback",
                "historical_context",
            }
        ),
        "explanation": frozenset(
            {
                "recommendation",
                "job_run_ingest",
                "pattern_analysis",
                "risk_assessment",
            }
        ),
    },
    SPARK_JOB_RCA_AGENT_ID: {
        "rca": frozenset(
            {
                "workspace_id",
                "job_id",
                "job_run_id",
                "job_run_date",
                "task_key",
                "classification_hint",
                "cluster_logs_section",
                "spark_metrics_section",
                "query_plans_section",
                "evidence_pack",
            }
        ),
    },
}


def validate_prompt_template(agent_id: str, chain_name: str, role: str, content: str) -> None:
    """Raise ValueError when required LangChain placeholders are missing."""
    text = (content or "").strip()
    if not text:
        raise ValueError("Prompt content cannot be empty")
    required = _CHAIN_PLACEHOLDER_KEYS.get(agent_id, {}).get(chain_name)
    if role == "human" and required:
        missing = [f"{{{k}}}" for k in sorted(required) if f"{{{k}}}" not in text]
        if missing:
            raise ValueError(f"Human prompt missing required placeholders: {', '.join(missing)}")
