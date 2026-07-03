"""Build effective Settings overrides from a workspace agent and its connections."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from shared.config.agent_manifest import role_kind, validate_bindings
from shared.config.connection_credentials import resolve_connection_secrets
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS
from shared.config.profile_overrides import flatten_overrides, validate_profile_overrides


def _connection_to_settings_flat(
    connection_type: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    if connection_type == "ai_foundry":
        for k in (
            "azure_openai_endpoint",
            "azure_openai_deployment_name",
            "azure_openai_embedding_deployment",
        ):
            if config.get(k):
                flat[k] = config[k]
    elif connection_type == "ai_search":
        flat["vector_retrieval_backend"] = "azure_search"
        for k in ("azure_search_endpoint", "azure_search_index_name"):
            if config.get(k):
                flat[k] = config[k]
    elif connection_type == "faiss":
        flat["vector_retrieval_backend"] = "faiss"
        if config.get("faiss_index_path"):
            flat["faiss_index_path"] = config["faiss_index_path"]
        if config.get("faiss_storage_type"):
            flat["faiss_storage_type"] = config["faiss_storage_type"]
    return flat


def _metrics_dataset_to_settings_flat(
    metrics_dataset: Dict[str, Any],
    metrics_wh_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    source_type = (metrics_dataset.get("source_type") or "").strip()
    if source_type == "databricks_delta":
        flat["use_local_data"] = False
        cfg = metrics_wh_config or {}
        for k in ("databricks_server_hostname", "databricks_http_path"):
            if cfg.get(k):
                flat[k] = cfg[k]
        table = (metrics_dataset.get("table_fqn") or "").strip()
        if table:
            flat["databricks_job_cluster_metrics_table"] = table
    elif source_type == "local_csv":
        flat["use_local_data"] = True
        path = (metrics_dataset.get("local_path") or "").strip()
        if path:
            flat["local_data_path"] = path
    return flat


def resolve_workspace_agent_settings(
    *,
    agent_id: str,
    bindings: Dict[str, Any],
    agent_settings: Dict[str, Any],
    connections: List[Dict[str, Any]],
    metrics_dataset: Optional[Dict[str, Any]] = None,
    metrics_wh_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (flat_overrides, secrets) for get_agent_settings merge."""
    types_by_id = {str(c["id"]): c["connection_type"] for c in connections}
    ds_profiles: Dict[str, str] = {}
    if metrics_dataset and metrics_dataset.get("id"):
        ds_profiles[str(metrics_dataset["id"])] = str(metrics_dataset.get("schema_profile") or "")
    normalized_bindings = validate_bindings(agent_id, bindings, types_by_id, ds_profiles)

    flat: Dict[str, Any] = {}
    secrets: Dict[str, Any] = {}

    metrics_binding_id = normalized_bindings.get("metrics")
    if metrics_binding_id and metrics_dataset:
        flat.update(_metrics_dataset_to_settings_flat(metrics_dataset, metrics_wh_config))

    for role, cid in normalized_bindings.items():
        if role == "metrics":
            continue
        conn = next((c for c in connections if str(c["id"]) == cid), None)
        if not conn:
            raise ValueError(f"Connection not found: {cid}")
        ctype = conn["connection_type"]
        cfg = conn.get("config") or {}
        flat.update(_connection_to_settings_flat(ctype, cfg))
        secrets.update(resolve_connection_secrets(ctype, UUID(str(conn["id"])), cfg))

    if agent_settings:
        allowed = set(PROFILE_ALLOWED_FIELDS)
        flat_agent = {k: v for k, v in flatten_overrides(agent_settings).items() if k in allowed}
        flat.update(validate_profile_overrides(flat_agent, allowed_fields=allowed))

    # Optional rag role: omit from bindings => no knowledge search for this install.
    if "rag" not in normalized_bindings:
        flat["vector_retrieval_backend"] = "none"

    return flat, secrets


def rag_binding_present(bindings: Dict[str, Any]) -> bool:
    """True when workspace agent bindings include an explicit rag connection/dataset id."""
    rag_id = (bindings or {}).get("rag")
    return bool(rag_id and str(rag_id).strip())


def load_connections_for_workspace_agent(
    workspace_agent_id: UUID,
    fetch_agent,
    fetch_connections,
) -> Tuple[str, str, Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Helper for services: fetch agent row and connection rows."""
    agent_row = fetch_agent(workspace_agent_id)
    if not agent_row:
        raise LookupError("Workspace agent not found")

    bindings = agent_row.get("bindings") or {}
    conn_ids = [UUID(v) for v in bindings.values() if v and str(v) != "agent_settings"]
    connections = fetch_connections(conn_ids) if conn_ids else []
    flat, secrets = resolve_workspace_agent_settings(
        agent_id=agent_row["agent_id"],
        bindings=bindings,
        agent_settings=agent_row.get("agent_settings") or {},
        connections=connections,
    )
    return agent_row["agent_id"], agent_row["workspace_id"], flat, secrets, connections
