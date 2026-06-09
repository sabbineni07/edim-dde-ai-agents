"""Per-agent connection role requirements for workspace agent bindings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

ROLE_UI: Dict[str, Dict[str, str]] = {
    "metrics": {
        "label": "Job metrics",
        "help": "Required. Databricks SQL warehouse or local CSV where job run data lives.",
    },
    "llm": {
        "label": "Language model",
        "help": "Optional. Azure OpenAI endpoint for recommendations and explanations.",
    },
    "rag": {
        "label": "Knowledge search",
        "help": "Optional. Azure AI Search or local FAISS index for extra context.",
    },
}

# role -> allowed connection types
AGENT_MANIFESTS: Dict[str, Dict[str, Any]] = {
    "dbx_cluster_tuning_agent": {
        "roles": {
            "metrics": ["databricks", "local_dataset"],
            "llm": ["ai_foundry"],
            "rag": ["ai_search", "faiss"],
        },
        "required_roles": ["metrics"],
        "optional_roles": ["llm", "rag"],
    },
}

WORKSPACE_AGENT_SETTINGS_KEYS = [
    "recommendation_auto_termination_minutes",
    "recommendation_cost_retry_enabled",
    "default_confidence_score",
    "guardrail_max_date_range_days",
]


def get_agent_manifest(agent_id: str) -> Optional[Dict[str, Any]]:
    return AGENT_MANIFESTS.get(agent_id)


def allowed_types_for_role(agent_id: str, role: str) -> List[str]:
    manifest = get_agent_manifest(agent_id)
    if not manifest:
        return []
    return list(manifest.get("roles", {}).get(role, []))


def validate_bindings(
    agent_id: str,
    bindings: Dict[str, Any],
    connection_types_by_id: Dict[str, str],
) -> Dict[str, str]:
    """Validate bindings map role -> connection_id. Returns normalized role -> id string."""
    manifest = get_agent_manifest(agent_id)
    if not manifest:
        raise ValueError(f"No manifest for agent_id: {agent_id}")

    required: Set[str] = set(manifest.get("required_roles", []))
    optional: Set[str] = set(manifest.get("optional_roles", []))
    allowed_roles = required | optional
    normalized: Dict[str, str] = {}

    for role, conn_id in (bindings or {}).items():
        if role == "agent_settings":
            continue
        if role not in allowed_roles:
            raise ValueError(f"Unknown binding role: {role}")
        if not conn_id:
            continue
        cid = str(conn_id)
        ctype = connection_types_by_id.get(cid)
        if not ctype:
            raise ValueError(f"Connection not found for role {role}: {cid}")
        allowed = manifest["roles"].get(role, [])
        if ctype not in allowed:
            raise ValueError(
                f"Connection type '{ctype}' not allowed for role '{role}' "
                f"(allowed: {', '.join(allowed)})"
            )
        normalized[role] = cid

    missing = required - set(normalized.keys())
    if missing:
        raise ValueError(f"Missing required bindings: {', '.join(sorted(missing))}")

    return normalized


def manifest_for_api(agent_id: str) -> Optional[Dict[str, Any]]:
    m = get_agent_manifest(agent_id)
    if not m:
        return None
    roles = m.get("roles", {})
    role_ui = {
        role: ROLE_UI.get(role, {"label": role, "help": ""})
        for role in set(m.get("required_roles", [])) | set(m.get("optional_roles", []))
    }
    return {
        "agent_id": agent_id,
        "roles": roles,
        "role_ui": role_ui,
        "required_roles": m.get("required_roles", []),
        "optional_roles": m.get("optional_roles", []),
        "agent_settings_keys": WORKSPACE_AGENT_SETTINGS_KEYS,
        "auth_note": (
            "Uses your Azure identity (az login or Managed Identity). "
            "Link connections below — no tokens or API keys are entered here."
        ),
    }
