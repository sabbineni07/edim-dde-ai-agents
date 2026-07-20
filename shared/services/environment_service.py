"""Resolve metrics table FQN and dataset helpers."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from shared.services.environment_connection_service import get_default_environment_connection
from shared.services.environment_dataset_service import (
    get_default_environment_dataset,
    get_environment_dataset,
)
from shared.services.local_dataset_service import get_active_file_path
from shared.services.platform_environment_service import PlatformEnvironment, get_environment
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _databricks_wh_ready(config: dict) -> bool:
    """SQL warehouse connection is usable (hostname + HTTP path)."""
    hostname = (config.get("databricks_server_hostname") or "").strip()
    http_path = (config.get("databricks_http_path") or "").strip()
    return bool(hostname and http_path)


def resolve_metrics_dataset_id(
    environment_id: str,
    dataset_id: Optional[str] = None,
    *,
    for_browse: bool = False,
) -> Optional[UUID]:
    """Resolve explicit or default dataset for browse or agent evidence APIs.

    When ``for_browse`` is True, the resolved dataset must use schema_profile
    ``job_inventory`` (environment browse inventory). Agent evidence datasets
    (e.g. job_cluster_metrics) are resolved with ``for_browse=False``.
    """
    from shared.config.dataset_profiles import require_browse_schema_profile

    eid = (environment_id or "").strip()
    if not eid:
        return None
    if dataset_id:
        try:
            did = UUID(dataset_id.strip())
        except ValueError as e:
            raise ValueError(f"Invalid dataset_id: {dataset_id}") from e
        ds = get_environment_dataset(did)
        if not ds:
            raise ValueError(f"Dataset not found: {dataset_id}")
        if ds.environment_id != eid:
            raise ValueError(f"Dataset {dataset_id} does not belong to environment {eid}")
        if for_browse:
            require_browse_schema_profile(ds.schema_profile)
        return did

    env = get_environment(eid)
    if env and env.default_dataset_id:
        try:
            did = UUID(env.default_dataset_id)
        except ValueError:
            did = None
        else:
            ds = get_environment_dataset(did)
            if ds and ds.environment_id == eid:
                if for_browse:
                    require_browse_schema_profile(ds.schema_profile)
                return did

    ds = get_default_environment_dataset(eid)
    if not ds:
        if for_browse:
            raise ValueError(
                "No job inventory browse dataset is configured. "
                "Add a dataset with schema profile 'job_inventory' and set it as the "
                "environment default on the Datasets page."
            )
        return None
    if for_browse:
        require_browse_schema_profile(ds.schema_profile)
    return ds.id


def resolve_metrics_table_fqn(
    environment_id: str,
    connection_config: Optional[dict] = None,
    *,
    dataset_id: Optional[str] = None,
    for_browse: bool = False,
) -> str:
    """Resolve the Delta table/view FQN for an environment dataset.

    Priority: explicit dataset_id → default environment dataset → legacy table on
    connection config (deprecated). Environment ``table_fqn`` columns are not used
    at runtime; configure a dataset instead.
    """
    eid = (environment_id or "").strip()
    resolved_id = (
        resolve_metrics_dataset_id(eid, dataset_id, for_browse=for_browse) if eid else None
    )
    if resolved_id:
        ds = get_environment_dataset(resolved_id)
        if ds and ds.source_type == "databricks_delta":
            return (ds.table_fqn or "").strip()

    if for_browse:
        return ""

    ds = get_default_environment_dataset(eid) if eid else None
    if ds and ds.source_type == "databricks_delta":
        table = (ds.table_fqn or "").strip()
        if table:
            return table

    legacy = ((connection_config or {}).get("databricks_job_cluster_metrics_table") or "").strip()
    if legacy:
        logger.warning(
            "deprecated_metrics_table_on_connection",
            environment_id=eid,
            table=legacy,
            message=(
                "Table on Databricks connection is deprecated; "
                "configure a dataset or catalog/schema/table on the environment."
            ),
        )
        return legacy
    return ""


def _has_metrics_dataset(env: PlatformEnvironment) -> bool:
    ds = get_default_environment_dataset(env.id)
    if ds:
        if ds.source_type == "databricks_delta":
            return bool((ds.table_fqn or "").strip())
        if ds.source_type == "local_csv":
            return bool((ds.local_path or "").strip())
    return False


def _metrics_table_ready(env: PlatformEnvironment, conn_config: Optional[dict] = None) -> bool:
    return _has_metrics_dataset(env) or bool(resolve_metrics_table_fqn(env.id, conn_config))


def _legacy_databricks_ready(env: PlatformEnvironment) -> bool:
    return _databricks_wh_ready(
        {
            "databricks_server_hostname": env.databricks_server_hostname,
            "databricks_http_path": env.databricks_http_path,
        }
    ) and _metrics_table_ready(env)


def _databricks_ready(env: PlatformEnvironment) -> bool:
    if not _has_metrics_dataset(env):
        return False
    conn = get_default_environment_connection(env.id, "metrics")
    if conn and conn.connection_type == "databricks":
        return _databricks_wh_ready(conn.config)
    return _legacy_databricks_ready(env)


def environment_readiness(
    environment_id: str,
    user_id: Optional[str] = None,
    *,
    local_fallback_path: Optional[str] = None,
    local_dataset_key: str = "default",
    local_stored_filename: str = "dataset.csv",
) -> str:
    """ready | needs_connection | needs_upload | unknown"""
    env = get_environment(environment_id)
    if not env:
        return "unknown"
    if not env.is_enabled:
        return "unknown"
    if env.source_type == "local_csv":
        ds = get_default_environment_dataset(env.id)
        if ds and ds.source_type == "local_csv" and ds.local_path:
            from shared.services.local_dataset_service import resolve_dataset_local_path

            if resolve_dataset_local_path(ds.local_path):
                return "ready"
        path = get_active_file_path(
            user_id or "anonymous",
            dataset_key=local_dataset_key,
            stored_filename=local_stored_filename,
            fallback_path=local_fallback_path,
        )
        return "ready" if path.is_file() else "needs_upload"
    return "ready" if _databricks_ready(env) else "needs_connection"


def resolve_metrics_connection_id(
    environment_id: str,
    connection_id: Optional[str] = None,
) -> Optional[UUID]:
    """Resolve explicit or default metrics connection for browse APIs."""
    if connection_id:
        try:
            return UUID(connection_id.strip())
        except ValueError:
            return None
    conn = get_default_environment_connection(environment_id, "metrics")
    if conn:
        return conn.id
    env = get_environment(environment_id)
    if env and env.default_metrics_connection_id:
        try:
            return UUID(env.default_metrics_connection_id)
        except ValueError:
            pass
    return None
