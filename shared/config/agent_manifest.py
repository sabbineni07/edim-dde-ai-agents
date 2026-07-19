"""Per-agent connection / dataset role requirements for workspace agent bindings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Union

RoleSpec = Union[List[str], Dict[str, Any]]

ROLE_UI: Dict[str, Dict[str, str]] = {
    "metrics": {
        "label": "Job cluster metrics dataset",
        "help": (
            "Required. Utilization metrics (job_cluster_metrics profile) for cluster sizing. "
            "Not the environment browse inventory."
        ),
    },
    "spark_logs": {
        "label": "Spark logs dataset",
        "help": "Required. Delta table (or local CSV/JSON) with spark application logs (RCA evidence).",
    },
    "spark_metrics": {
        "label": "Spark metrics dataset",
        "help": "Required. Delta table (or local CSV/JSON) with spark job/SQL/stage telemetry (RCA evidence).",
    },
    "llm": {
        "label": "Language model",
        "help": "Required. Azure OpenAI endpoint for recommendations and explanations.",
    },
    "rag": {
        "label": "Knowledge search",
        "help": "Optional. Azure AI Search or local FAISS index for extra context.",
    },
}

AGENT_MANIFESTS: Dict[str, Dict[str, Any]] = {
    "dbx_cluster_tuning_agent": {
        "roles": {
            "metrics": {"kind": "dataset", "schema_profile": "job_cluster_metrics"},
            "llm": {"kind": "connection", "connection_types": ["ai_foundry"]},
            "rag": {"kind": "connection", "connection_types": ["ai_search", "faiss"]},
        },
        "required_roles": ["metrics", "llm"],
        "optional_roles": ["rag"],
    },
    "spark_job_rca_agent": {
        "roles": {
            "spark_logs": {"kind": "dataset", "schema_profile": "spark_logs"},
            "spark_metrics": {"kind": "dataset", "schema_profile": "spark_metrics"},
            "llm": {"kind": "connection", "connection_types": ["ai_foundry"]},
        },
        "required_roles": ["spark_logs", "spark_metrics", "llm"],
        "optional_roles": [],
    },
}

WORKSPACE_AGENT_SETTINGS_KEYS = [
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


def get_agent_manifest(agent_id: str) -> Optional[Dict[str, Any]]:
    return AGENT_MANIFESTS.get(agent_id)


def role_kind(role_spec: Any) -> str:
    if isinstance(role_spec, dict):
        return str(role_spec.get("kind") or "connection")
    return "connection"


def connection_types_for_role(role_spec: Any) -> List[str]:
    if isinstance(role_spec, list):
        return list(role_spec)
    if isinstance(role_spec, dict) and role_kind(role_spec) == "connection":
        return list(role_spec.get("connection_types") or [])
    return []


def dataset_profile_for_role(role_spec: Any) -> Optional[str]:
    if isinstance(role_spec, dict) and role_kind(role_spec) == "dataset":
        profile = (role_spec.get("schema_profile") or "").strip()
        return profile or None
    return None


def allowed_types_for_role(agent_id: str, role: str) -> List[str]:
    manifest = get_agent_manifest(agent_id)
    if not manifest:
        return []
    return connection_types_for_role(manifest.get("roles", {}).get(role))


def validate_bindings(
    agent_id: str,
    bindings: Dict[str, Any],
    connection_types_by_id: Dict[str, str],
    dataset_profiles_by_id: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Validate bindings map role -> connection_id or dataset_id."""
    manifest = get_agent_manifest(agent_id)
    if not manifest:
        raise ValueError(f"No manifest for agent_id: {agent_id}")

    required: Set[str] = set(manifest.get("required_roles", []))
    optional: Set[str] = set(manifest.get("optional_roles", []))
    allowed_roles = required | optional
    roles_spec: Dict[str, Any] = manifest.get("roles", {})
    normalized: Dict[str, str] = {}
    ds_profiles = dataset_profiles_by_id or {}

    for role, binding_id in (bindings or {}).items():
        if role == "agent_settings":
            continue
        if role not in allowed_roles:
            raise ValueError(f"Unknown binding role: {role}")
        if not binding_id:
            continue
        bid = str(binding_id)
        spec = roles_spec.get(role)

        if role_kind(spec) == "dataset":
            profile = ds_profiles.get(bid)
            if not profile:
                raise ValueError(f"Dataset not found for role {role}: {bid}")
            required_profile = dataset_profile_for_role(spec)
            if required_profile and profile != required_profile:
                raise ValueError(
                    f"Dataset for role '{role}' must use schema_profile "
                    f"'{required_profile}' (got '{profile}')"
                )
            normalized[role] = bid
            continue

        ctype = connection_types_by_id.get(bid)
        if not ctype:
            raise ValueError(f"Connection not found for role {role}: {bid}")
        allowed = connection_types_for_role(spec)
        if ctype not in allowed:
            raise ValueError(
                f"Connection type '{ctype}' not allowed for role '{role}' "
                f"(allowed: {', '.join(allowed)})"
            )
        normalized[role] = bid

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
            "Link datasets and connections below — no tokens or API keys are entered here."
        ),
    }
