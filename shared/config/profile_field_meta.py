"""UI metadata and allowlist for workspace agent_settings fields.

Connection bindings supply LLM (AI Foundry) and RAG (Search/FAISS) config.
Advanced settings here are agent-behavior knobs only — no duplicate deployment/model fields.
"""

from __future__ import annotations

from typing import Any, Dict, List

PROFILE_ALLOWED_FIELDS = [
    "recommendation_auto_termination_minutes",
    "recommendation_cost_retry_enabled",
    "llm_temperature",
    "llm_top_p",
    "sizing_llm_temperature",
    "sizing_llm_top_p",
    "explanation_llm_temperature",
    "explanation_llm_top_p",
    "rag_top_k_recommendations",
    "rag_top_k_jobs",
]

PROFILE_FIELD_UI: Dict[str, Dict[str, Any]] = {
    "recommendation_auto_termination_minutes": {
        "label": "Auto-termination (minutes)",
        "type": "number",
        "min": 0,
        "group": "recommendation",
        "help": "Suggested cluster auto-shutdown after job completion (0 = no suggestion).",
    },
    "recommendation_cost_retry_enabled": {
        "label": "Cost retry when guardrails adjust",
        "type": "boolean",
        "group": "recommendation",
        "help": "Re-run cost estimate if guardrails change the recommendation.",
    },
    "llm_temperature": {
        "label": "Temperature (default)",
        "type": "number",
        "min": 0,
        "max": 2,
        "step": 0.1,
        "group": "llm_sampling",
        "help": "Default sampling temperature for sizing and explanation. Use 0 for deterministic JSON sizing.",
    },
    "llm_top_p": {
        "label": "Top P (default)",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "group": "llm_sampling",
        "help": "Nucleus sampling ceiling. Usually leave at 1.0 when temperature is 0.",
    },
    "sizing_llm_temperature": {
        "label": "Sizing temperature (override)",
        "type": "number",
        "min": 0,
        "max": 2,
        "step": 0.1,
        "group": "llm_sampling",
        "help": "Optional override for the sizing JSON chain only. Blank uses default temperature.",
        "placeholder": "Default",
    },
    "sizing_llm_top_p": {
        "label": "Sizing top P (override)",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "group": "llm_sampling",
        "help": "Optional override for sizing chain only.",
        "placeholder": "Default",
    },
    "explanation_llm_temperature": {
        "label": "Explanation temperature (override)",
        "type": "number",
        "min": 0,
        "max": 2,
        "step": 0.1,
        "group": "llm_sampling",
        "help": "Optional override for the explanation chain (e.g. 0.2 for slightly varied prose).",
        "placeholder": "Default",
    },
    "explanation_llm_top_p": {
        "label": "Explanation top P (override)",
        "type": "number",
        "min": 0,
        "max": 1,
        "step": 0.05,
        "group": "llm_sampling",
        "help": "Optional override for explanation chain only.",
        "placeholder": "Default",
    },
    "rag_top_k_recommendations": {
        "label": "Retrieval: max similar recommendations",
        "type": "number",
        "min": 1,
        "max": 20,
        "step": 1,
        "group": "rag_retrieval",
        "help": "RAG only — how many approved recommendation docs to retrieve (when Knowledge search is bound).",
    },
    "rag_top_k_jobs": {
        "label": "Retrieval: max similar job patterns",
        "type": "number",
        "min": 1,
        "max": 20,
        "step": 1,
        "group": "rag_retrieval",
        "help": "RAG only — how many job metrics docs to retrieve when no recommendation hits exist.",
    },
}

PROFILE_FIELD_GROUPS: Dict[str, str] = {
    "recommendation": "Recommendation behavior",
    "llm_sampling": "Language model sampling",
    "rag_retrieval": "Knowledge search retrieval",
}


def editable_profile_fields() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key in PROFILE_ALLOWED_FIELDS:
        meta = dict(PROFILE_FIELD_UI.get(key, {"label": key, "type": "string"}))
        meta["key"] = key
        out.append(meta)
    return out
