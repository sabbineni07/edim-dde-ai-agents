"""Build effective Settings overrides from a workspace agent and its connections."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from shared.config.agent_manifest import get_agent_manifest, role_kind, validate_bindings
from shared.config.connection_credentials import resolve_connection_secrets
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS
from shared.config.profile_overrides import flatten_overrides, validate_profile_overrides

# Dataset role -> settings keys for Delta table FQN and local path.
_DATASET_SETTINGS_KEYS: Dict[str, Tuple[str, str]] = {
    "metrics": ("databricks_job_cluster_metrics_table", "local_data_path"),
    "spark_logs": ("databricks_spark_logs_table", "local_spark_logs_path"),
    "spark_metrics": ("databricks_spark_metrics_table", "local_spark_metrics_path"),
}


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
            "databricks_service_credential_name",
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


def _dataset_to_settings_flat(role: str, dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Map a bound dataset to flat settings keys for the given role."""
    keys = _DATASET_SETTINGS_KEYS.get(role)
    if not keys:
        return {}
    table_key, path_key = keys
    flat: Dict[str, Any] = {}
    source_type = (dataset.get("source_type") or "").strip()
    if source_type == "databricks_delta":
        if role == "metrics":
            flat["use_local_data"] = False
        table = (dataset.get("table_fqn") or "").strip()
        if table:
            flat[table_key] = table
    elif source_type == "local_csv":
        if role == "metrics":
            flat["use_local_data"] = True
        path = (dataset.get("local_path") or "").strip()
        if path:
            flat[path_key] = path
    return flat


def _metrics_dataset_to_settings_flat(
    metrics_dataset: Dict[str, Any],
    metrics_wh_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Backward-compatible wrapper for the metrics role."""
    return _dataset_to_settings_flat("metrics", metrics_dataset)


def _apply_databricks_wh_config(
    flat: Dict[str, Any],
    metrics_wh_config: Optional[Dict[str, Any]],
) -> None:
    """Merge SQL warehouse host/path from the environment's Databricks connection."""
    cfg = metrics_wh_config or {}
    for key in ("databricks_server_hostname", "databricks_http_path"):
        if cfg.get(key):
            flat[key] = cfg[key]


def resolve_workspace_agent_settings(
    *,
    agent_id: str,
    bindings: Dict[str, Any],
    agent_settings: Dict[str, Any],
    connections: List[Dict[str, Any]],
    metrics_dataset: Optional[Dict[str, Any]] = None,
    metrics_wh_config: Optional[Dict[str, Any]] = None,
    datasets_by_role: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (flat_overrides, secrets) for get_agent_settings merge.

    ``datasets_by_role`` maps binding role name -> dataset record dict.
    ``metrics_dataset`` is kept for backward compatibility and merges into
    ``datasets_by_role["metrics"]`` when provided.
    """
    types_by_id = {str(c["id"]): c["connection_type"] for c in connections}
    role_datasets: Dict[str, Dict[str, Any]] = dict(datasets_by_role or {})
    if metrics_dataset and metrics_dataset.get("id"):
        role_datasets.setdefault("metrics", metrics_dataset)

    ds_profiles: Dict[str, str] = {}
    for ds in role_datasets.values():
        if ds and ds.get("id"):
            ds_profiles[str(ds["id"])] = str(ds.get("schema_profile") or "")

    normalized_bindings = validate_bindings(agent_id, bindings, types_by_id, ds_profiles)

    flat: Dict[str, Any] = {}
    secrets: Dict[str, Any] = {}

    manifest = get_agent_manifest(agent_id) or {}
    roles_spec = manifest.get("roles", {})

    for role, binding_id in normalized_bindings.items():
        spec = roles_spec.get(role)
        if role_kind(spec) != "dataset":
            continue
        ds = role_datasets.get(role)
        if ds:
            flat.update(_dataset_to_settings_flat(role, ds))

    if metrics_wh_config:
        _apply_databricks_wh_config(flat, metrics_wh_config)

    for role, cid in normalized_bindings.items():
        spec = roles_spec.get(role)
        if role_kind(spec) == "dataset":
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
