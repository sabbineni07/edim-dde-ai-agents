"""Resolve job-metrics data collectors for a platform environment (jobs browse use case)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from DE.src.datasets.job_cluster_metrics_csv import LOCAL_DATASET_KEY, STORED_FILENAME
from shared.services.environment_connection_service import get_environment_connection
from shared.services.environment_service import resolve_metrics_connection_id
from shared.services.local_dataset_service import get_active_file_path, resolve_fallback_path
from shared.services.platform_environment_service import get_environment
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _collector_from_databricks_config(
    config: dict, *, environment_id: str, connection_id: Optional[UUID]
):
    from DE.src.collectors.databricks_collector import DatabricksCollector

    hostname = (config.get("databricks_server_hostname") or "").strip()
    http_path = (config.get("databricks_http_path") or "").strip()
    table = (config.get("databricks_job_cluster_metrics_table") or "").strip()
    if not (hostname and http_path and table):
        raise ValueError(
            "Databricks metrics connection is incomplete. "
            "Set SQL warehouse host, HTTP path, and metrics table in Connections."
        )
    logger.info(
        "job_metrics_collector_databricks",
        environment_id=environment_id,
        connection_id=str(connection_id) if connection_id else None,
        table=table,
    )
    return DatabricksCollector(
        metrics_table=table,
        server_hostname=hostname,
        http_path=http_path,
    )


def get_collector(
    environment_id: str,
    user_id: Optional[str] = None,
    *,
    connection_id: Optional[str] = None,
):
    """Build a collector for workspace/job browse APIs (job cluster metrics)."""
    env = get_environment(environment_id)
    if not env:
        raise ValueError(f"Unknown environment: {environment_id}")

    if env.source_type == "local_csv":
        from DE.src.collectors.local_data_collector import LocalDataCollector

        fallback = str(resolve_fallback_path())
        csv_path = get_active_file_path(
            user_id or "anonymous",
            dataset_key=LOCAL_DATASET_KEY,
            stored_filename=STORED_FILENAME,
            fallback_path=fallback,
        )
        logger.info(
            "job_metrics_collector_local",
            environment_id=environment_id,
            csv_path=str(csv_path),
        )
        return LocalDataCollector(csv_path=str(csv_path))

    resolved_id = resolve_metrics_connection_id(environment_id, connection_id)
    if resolved_id:
        conn = get_environment_connection(resolved_id)
        if conn and conn.environment_id == environment_id and conn.purpose == "metrics":
            if conn.connection_type == "databricks":
                return _collector_from_databricks_config(
                    conn.config,
                    environment_id=environment_id,
                    connection_id=resolved_id,
                )

    # Legacy fallback: fields still on platform_environments row
    hostname = (env.databricks_server_hostname or "").strip()
    http_path = (env.databricks_http_path or "").strip()
    table = env.table_fqn or ""
    if hostname and http_path and table:
        return _collector_from_databricks_config(
            {
                "databricks_server_hostname": hostname,
                "databricks_http_path": http_path,
                "databricks_job_cluster_metrics_table": table,
            },
            environment_id=environment_id,
            connection_id=None,
        )

    raise ValueError(
        f"Databricks is not configured for environment '{env.display_name}'. "
        "Add a default metrics connection in Connections."
    )
