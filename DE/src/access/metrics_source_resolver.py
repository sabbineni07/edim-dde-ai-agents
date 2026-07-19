"""Resolve metrics collector + dataset/connection context for browse and recommend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from DE.src.datasets.job_cluster_metrics_csv import LOCAL_DATASET_KEY, STORED_FILENAME
from shared.services.environment_connection_service import get_environment_connection
from shared.services.environment_dataset_service import get_environment_dataset
from shared.services.environment_service import (
    resolve_metrics_connection_id,
    resolve_metrics_dataset_id,
    resolve_metrics_table_fqn,
)
from shared.services.local_dataset_service import get_active_file_path, resolve_fallback_path
from shared.services.platform_environment_service import get_environment
from shared.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MetricsSourceContext:
    environment_id: str
    connection_id: Optional[str]
    dataset_id: Optional[str]
    dataset_name: Optional[str]
    table_fqn: Optional[str]
    source_type: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "connection_id": self.connection_id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "table_fqn": self.table_fqn,
            "source_type": self.source_type,
        }


def _collector_from_databricks_config(
    config: dict,
    *,
    environment_id: str,
    connection_id: Optional[UUID],
    metrics_table: str,
    dataset_id: Optional[str],
    dataset_name: Optional[str],
) -> tuple[Any, MetricsSourceContext]:
    from DE.src.collectors.databricks_collector import DatabricksCollector
    from shared.databricks.sql_config import require_databricks_sql_config

    sql_cfg = require_databricks_sql_config(config)
    hostname = sql_cfg["databricks_server_hostname"]
    http_path = sql_cfg["databricks_http_path"]
    table = (metrics_table or "").strip()
    if not table:
        raise ValueError(
            "Metrics dataset is not configured. "
            "Add a default dataset or select one in the browse header."
        )
    logger.info(
        "job_metrics_collector_databricks",
        environment_id=environment_id,
        connection_id=str(connection_id) if connection_id else None,
        dataset_id=dataset_id,
        table=table,
        server_hostname=hostname,
        http_path=http_path,
    )
    collector = DatabricksCollector(
        metrics_table=table,
        server_hostname=hostname,
        http_path=http_path,
    )
    ctx = MetricsSourceContext(
        environment_id=environment_id,
        connection_id=str(connection_id) if connection_id else None,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        table_fqn=table,
        source_type="databricks_delta",
    )
    return collector, ctx


def resolve_metrics_source(
    environment_id: str,
    user_id: Optional[str] = None,
    *,
    connection_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    for_browse: bool = True,
) -> tuple[Any, MetricsSourceContext]:
    """Build collector and resolved dataset/connection metadata.

    ``for_browse=True`` (default) requires a ``job_inventory`` dataset for Workspaces/Jobs/Runs.
    Pass ``for_browse=False`` when resolving agent evidence (e.g. job_cluster_metrics for tuning).
    """
    env = get_environment(environment_id)
    if not env:
        raise ValueError(f"Unknown environment: {environment_id}")

    resolved_dataset_uuid = resolve_metrics_dataset_id(
        environment_id, dataset_id, for_browse=for_browse
    )
    resolved_dataset_id = str(resolved_dataset_uuid) if resolved_dataset_uuid else None
    ds_rec = get_environment_dataset(resolved_dataset_uuid) if resolved_dataset_uuid else None
    ds_name = ds_rec.name if ds_rec else None

    if env.source_type == "local_csv":
        from DE.src.collectors.local_data_collector import LocalDataCollector

        csv_path = None
        if ds_rec and ds_rec.source_type == "local_csv" and ds_rec.local_path:
            candidate = Path(ds_rec.local_path)
            if candidate.is_file():
                csv_path = candidate
        if csv_path is None:
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
            dataset_id=resolved_dataset_id,
            csv_path=str(csv_path),
            for_browse=for_browse,
        )
        ctx = MetricsSourceContext(
            environment_id=environment_id,
            connection_id=None,
            dataset_id=resolved_dataset_id,
            dataset_name=ds_name,
            table_fqn=None,
            source_type="local_csv",
        )
        return LocalDataCollector(csv_path=str(csv_path)), ctx

    conn_config: dict = {}
    resolved_conn_uuid = resolve_metrics_connection_id(environment_id, connection_id)
    if resolved_conn_uuid:
        conn = get_environment_connection(resolved_conn_uuid)
        if conn and conn.environment_id == environment_id and conn.purpose == "metrics":
            if conn.connection_type == "databricks":
                conn_config = conn.config or {}
                table = resolve_metrics_table_fqn(
                    environment_id,
                    conn_config,
                    dataset_id=resolved_dataset_id,
                    for_browse=for_browse,
                )
                return _collector_from_databricks_config(
                    conn_config,
                    environment_id=environment_id,
                    connection_id=resolved_conn_uuid,
                    metrics_table=table,
                    dataset_id=resolved_dataset_id,
                    dataset_name=ds_name,
                )

    hostname = (env.databricks_server_hostname or "").strip()
    http_path = (env.databricks_http_path or "").strip()
    table = resolve_metrics_table_fqn(
        environment_id,
        dataset_id=resolved_dataset_id,
        for_browse=for_browse,
    )
    if hostname and http_path and table:
        return _collector_from_databricks_config(
            {
                "databricks_server_hostname": hostname,
                "databricks_http_path": http_path,
            },
            environment_id=environment_id,
            connection_id=None,
            metrics_table=table,
            dataset_id=resolved_dataset_id,
            dataset_name=ds_name,
        )

    raise ValueError(
        f"Databricks is not configured for environment '{env.display_name}'. "
        "Add a default metrics connection in Connections and a job inventory "
        "dataset (schema profile job_inventory) in Datasets."
    )


def get_collector(
    environment_id: str,
    user_id: Optional[str] = None,
    *,
    connection_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
    for_browse: bool = True,
):
    """Build a collector for workspace/job browse APIs (job inventory by default)."""
    collector, _ctx = resolve_metrics_source(
        environment_id,
        user_id,
        connection_id=connection_id,
        dataset_id=dataset_id,
        for_browse=for_browse,
    )
    return collector
