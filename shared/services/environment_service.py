"""Platform environment helpers — readiness from connections or legacy env fields."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from shared.services.environment_connection_service import get_default_environment_connection
from shared.services.local_dataset_service import get_active_file_path
from shared.services.platform_environment_service import PlatformEnvironment, get_environment
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _databricks_connection_ready(config: dict) -> bool:
    hostname = (config.get("databricks_server_hostname") or "").strip()
    http_path = (config.get("databricks_http_path") or "").strip()
    table = (config.get("databricks_job_cluster_metrics_table") or "").strip()
    return bool(hostname and http_path and table)


def _legacy_databricks_ready(env: PlatformEnvironment) -> bool:
    return bool(
        (env.databricks_server_hostname or "").strip()
        and (env.databricks_http_path or "").strip()
        and (env.table_fqn or "").strip()
    )


def _databricks_ready(env: PlatformEnvironment) -> bool:
    conn = get_default_environment_connection(env.id, "metrics")
    if conn and conn.connection_type == "databricks":
        return _databricks_connection_ready(conn.config)
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
