"""UI metadata and allowlist for workspace agent_settings fields.

Connection bindings supply LLM (AI Foundry) and RAG (Search/FAISS) config.
Advanced settings here are agent-behavior knobs only — no duplicate deployment/model fields.
"""

from __future__ import annotations

from typing import Any, Dict, List

PROFILE_ALLOWED_FIELDS = [
    "recommendation_auto_termination_minutes",
    "recommendation_cost_retry_enabled",
]

PROFILE_FIELD_UI: Dict[str, Dict[str, Any]] = {
    "recommendation_auto_termination_minutes": {
        "label": "Auto-termination (minutes)",
        "type": "number",
        "min": 0,
        "help": "Suggested cluster auto-shutdown after job completion (0 = no suggestion).",
    },
    "recommendation_cost_retry_enabled": {
        "label": "Cost retry when guardrails adjust",
        "type": "boolean",
        "help": "Re-run cost estimate if guardrails change the recommendation.",
    },
}


def editable_profile_fields() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in PROFILE_ALLOWED_FIELDS:
        meta = dict(PROFILE_FIELD_UI.get(key, {"label": key, "type": "string"}))
        meta["key"] = key
        out.append(meta)
    return out
