"""UI metadata and allowlist for agent profile override fields."""

from __future__ import annotations

from typing import Any, Dict, List

PROFILE_ALLOWED_FIELDS = [
    "azure_openai_deployment_name",
    "default_model_name",
    "vector_retrieval_backend",
    "recommendation_auto_termination_minutes",
    "recommendation_cost_retry_enabled",
    "default_confidence_score",
    "guardrail_max_date_range_days",
]

PROFILE_FIELD_UI: Dict[str, Dict[str, Any]] = {
    "azure_openai_deployment_name": {
        "label": "Azure OpenAI deployment",
        "type": "string",
        "placeholder": "gpt-4o",
    },
    "default_model_name": {
        "label": "Default model name",
        "type": "string",
        "placeholder": "gpt-4o",
    },
    "vector_retrieval_backend": {
        "label": "Vector retrieval backend",
        "type": "select",
        "options": ["azure", "none"],
    },
    "recommendation_auto_termination_minutes": {
        "label": "Auto-termination (minutes)",
        "type": "number",
        "min": 0,
    },
    "recommendation_cost_retry_enabled": {
        "label": "Cost retry when guardrails adjust",
        "type": "boolean",
    },
    "default_confidence_score": {
        "label": "Default confidence score",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
    },
    "guardrail_max_date_range_days": {
        "label": "Max date range (days)",
        "type": "number",
        "min": 1,
        "max": 365,
    },
}


def editable_profile_fields() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in PROFILE_ALLOWED_FIELDS:
        meta = dict(PROFILE_FIELD_UI.get(key, {"label": key, "type": "string"}))
        meta["key"] = key
        out.append(meta)
    return out
