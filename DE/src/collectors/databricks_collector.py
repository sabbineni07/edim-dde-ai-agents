"""Databricks data collector: reads pre-aggregated job metrics from a centralized Delta table."""

from typing import Any, Dict, List, Optional

from databricks import sql

from shared.config.settings import settings
from shared.models.job_cluster_metrics import (
    DELTA_MEMORY_EFFICIENCY_SQL_EXPR,
    DELTA_WORKER_NODE_PROVISIONING_EFFICIENCY_SQL_EXPR,
    JobClusterMetrics,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_METRICS_SELECT = f"""
SELECT
  CAST(job_run_date AS STRING) AS job_run_date,
  CAST(workspace_id AS STRING) AS workspace_id,
  workspace_name,
  CAST(cluster_id AS STRING) AS cluster_id,
  CAST(job_id AS STRING) AS job_id,
  job_type,
  job_name,
  CAST(job_run_start_time_utc AS STRING) AS job_run_start_time_utc,
  CAST(job_run_end_time_utc AS STRING) AS job_run_end_time_utc,
  COALESCE(CAST(job_run_duration_seconds AS DOUBLE), 0.0) AS job_run_duration_seconds,
  azure_driver_vm_size,
  COALESCE(CAST(driver_node_count AS BIGINT), 1) AS driver_node_count,
  CAST(driver_vcpus_consumed AS DOUBLE) AS driver_vcpus_consumed,
  CAST(driver_memory_gb_consumed AS DOUBLE) AS driver_memory_gb_consumed,
  CAST(avg_driver_cpu_utilization_pct AS DOUBLE) AS avg_driver_cpu_utilization_pct,
  CAST(avg_driver_memory_utilization_pct AS DOUBLE) AS avg_driver_memory_utilization_pct,
  CAST(peak_driver_cpu_utilization_pct AS DOUBLE) AS peak_driver_cpu_utilization_pct,
  COALESCE(azure_worker_vm_size, 'Standard_E8s_v3') AS azure_worker_vm_size,
  COALESCE(CAST(max_worker_nodes_provisioned AS BIGINT), 1) AS max_worker_nodes_provisioned,
  CAST(total_worker_vcpus_provisioned AS DOUBLE) AS total_worker_vcpus_provisioned,
  CAST(total_worker_memory_gb_provisioned AS DOUBLE) AS total_worker_memory_gb_provisioned,
  COALESCE(CAST(avg_worker_nodes_consumed AS DOUBLE), 0.0) AS avg_worker_nodes_consumed,
  COALESCE(CAST(p99_worker_nodes_consumed AS DOUBLE), 0.0) AS p99_worker_nodes_consumed,
  CAST(avg_worker_vcpus_consumed AS DOUBLE) AS avg_worker_vcpus_consumed,
  CAST(avg_worker_memory_gb_consumed AS DOUBLE) AS avg_worker_memory_gb_consumed,
  CAST(avg_worker_vcpus_utilized AS DOUBLE) AS avg_worker_vcpus_utilized,
  CAST(avg_worker_memory_gb_utilized AS DOUBLE) AS avg_worker_memory_gb_utilized,
  COALESCE(CAST(avg_worker_cpu_utilization_pct AS DOUBLE), 0.0) AS avg_worker_cpu_utilization_pct,
  COALESCE(CAST(avg_worker_memory_utilization_pct AS DOUBLE), 0.0) AS avg_worker_memory_utilization_pct,
  COALESCE(CAST(peak_worker_cpu_utilization_pct AS DOUBLE), 0.0) AS peak_worker_cpu_utilization_pct,
  COALESCE(CAST(peak_worker_memory_utilization_pct AS DOUBLE), 0.0) AS peak_worker_memory_utilization_pct,
  {DELTA_WORKER_NODE_PROVISIONING_EFFICIENCY_SQL_EXPR} AS worker_node_provisioning_efficiency_pct,
  CAST(worker_cpu_utilization_efficiency_pct AS DOUBLE) AS worker_cpu_utilization_efficiency_pct,
  {DELTA_MEMORY_EFFICIENCY_SQL_EXPR} AS worker_memory_utilization_efficency_pct,
  CAST(delta_tables_ingested AS BIGINT) AS delta_tables_ingested,
  CAST(processed_bytes AS BIGINT) AS processed_bytes,
  CAST(processed_row_count AS BIGINT) AS processed_row_count
"""


class DatabricksCollector:
    """Collects job metrics from a pre-aggregated centralized Delta table only."""

    def __init__(
        self,
        *,
        metrics_table: Optional[str] = None,
        server_hostname: Optional[str] = None,
        http_path: Optional[str] = None,
    ):
        self._metrics_table = (
            metrics_table or settings.databricks_job_cluster_metrics_table or ""
        ).strip() or None
        self._server_hostname = server_hostname or settings.databricks_server_hostname
        self._http_path = http_path or settings.databricks_http_path

    def _connection_params(self) -> Dict[str, Any]:
        """Build SQL connector params; token from env override or Azure identity at runtime."""
        token = (settings.databricks_token or "").strip() or None
        if not token:
            try:
                from shared.auth.azure_tokens import DATABRICKS_AAD_SCOPE, get_azure_access_token

                token = get_azure_access_token(DATABRICKS_AAD_SCOPE)
                settings.databricks_token = token
                logger.debug("databricks_token_from_azure_identity", cached=True)
            except Exception as e:
                logger.warning(
                    "databricks_token_unavailable",
                    error=str(e),
                    hint="Run az login or assign Managed Identity with Databricks access.",
                )
        return {
            "server_hostname": self._server_hostname,
            "http_path": self._http_path,
            "access_token": token,
            "_socket_timeout": 30,
            "_query_timeout": 60,
        }

    def collect_job_cluster_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Collect job cluster metrics by job_id and date range from the centralized Delta table."""
        logger.info(
            "collecting_job_cluster_metrics",
            start_date=start_date,
            end_date=end_date,
            job_count=len(job_ids) if job_ids else None,
        )
        if not self._metrics_table:
            logger.warning(
                "databricks_job_cluster_metrics_table_not_set",
                message="DATABRICKS_JOB_CLUSTER_METRICS_TABLE is required; returning no metrics.",
            )
            return []
        return self._collect_from_delta_table(
            start_date, end_date, job_ids, workspace_id, job_run_id
        )

    def _collect_from_delta_table(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Fetch records from centralized Delta table by job_id and optional date range."""
        table = self._metrics_table
        run_only = bool(job_run_id and str(job_run_id).strip()) and not (start_date and end_date)
        conditions: List[str] = []
        params: List[Any] = []
        if not run_only:
            if not start_date or not end_date:
                logger.warning("databricks_missing_date_range")
                return []
            conditions.extend(["job_run_date >= ?", "job_run_date <= ?"])
            params.extend([start_date, end_date])
        if job_ids:
            placeholders = ", ".join(["?" for _ in job_ids])
            conditions.append(f"job_id IN ({placeholders})")
            params.extend(job_ids)
        if workspace_id:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        if job_run_id:
            conditions.append("CAST(cluster_id AS STRING) = ?")
            params.append(str(job_run_id))
        if not conditions:
            logger.warning("databricks_collect_metrics_no_filters")
            return []
        where = " AND ".join(conditions)
        query = f"""
        {_METRICS_SELECT}
        FROM {table}
        WHERE {where}
        ORDER BY job_run_date DESC, job_run_start_time_utc DESC
        LIMIT 1000
        """

        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description]
                    results = cursor.fetchall()
                    metrics = []
                    for row in results:
                        row_dict = dict(zip(columns, row))
                        try:
                            metrics.append(JobClusterMetrics.model_validate(row_dict))
                        except Exception as e:
                            logger.warning("failed_to_parse_delta_row", error=str(e), row=row_dict)
                    logger.info(
                        "collected_job_cluster_metrics_from_delta", count=len(metrics), table=table
                    )
                    return metrics
        except Exception as e:
            logger.error("databricks_collection_error", error=str(e), table=table)
            raise

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List distinct workspaces using SQL aggregation (COUNT DISTINCT job_id)."""
        if not self._metrics_table:
            logger.warning(
                "databricks_job_cluster_metrics_table_not_set",
                message="DATABRICKS_JOB_CLUSTER_METRICS_TABLE is required; returning no workspaces.",
            )
            return []

        table = self._metrics_table
        query = f"""
        SELECT
          CAST(workspace_id AS STRING) AS workspace_id,
          COALESCE(MAX(workspace_name), CAST(workspace_id AS STRING), 'unknown') AS workspace_name,
          CAST(COUNT(DISTINCT job_id) AS BIGINT) AS job_count,
          CAST(MIN(job_run_date) AS STRING) AS first_seen_date,
          CAST(MAX(job_run_date) AS STRING) AS last_seen_date
        FROM {table}
        GROUP BY workspace_id
        ORDER BY last_seen_date DESC, workspace_id
        """
        params: List[Any] = []

        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description]
                    results = cursor.fetchall()
                    workspaces = [dict(zip(columns, row)) for row in results]
                    logger.info("listed_workspaces_from_delta", count=len(workspaces), table=table)
                    return workspaces
        except Exception as e:
            logger.error("list_workspaces_error", error=str(e), table=table)
            raise

    def list_jobs_for_workspace(
        self, workspace_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """List aggregated jobs for a workspace directly from Delta table."""
        if not self._metrics_table:
            logger.warning(
                "databricks_job_cluster_metrics_table_not_set",
                message="DATABRICKS_JOB_CLUSTER_METRICS_TABLE is required; returning no jobs.",
            )
            return []

        table = self._metrics_table
        query = f"""
        SELECT
          CAST(job_id AS STRING) AS job_id,
          COALESCE(MAX(job_name), CAST(job_id AS STRING)) AS job_name,
          COALESCE(MAX(job_type)) AS job_type,
          COALESCE(AVG(avg_worker_cpu_utilization_pct), 0.0) AS avg_worker_cpu_utilization_pct,
          COALESCE(AVG(avg_worker_memory_utilization_pct), 0.0) AS avg_worker_memory_utilization_pct,
          CAST(COUNT(*) AS BIGINT) AS total_runs,
          COALESCE(AVG(job_run_duration_seconds), 0.0) AS avg_job_run_duration_seconds,
          COALESCE(MAX(azure_worker_vm_size), 'Standard_E8s_v3') AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          CAST(MAX(job_run_date) AS STRING) AS last_job_run_date
        FROM {table}
        WHERE workspace_id = ?
          AND job_run_date >= ?
          AND job_run_date <= ?
        GROUP BY job_id
        ORDER BY job_name, job_id
        """
        params: List[Any] = [workspace_id, start_date, end_date]

        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description]
                    results = cursor.fetchall()
                    jobs = [
                        {"workspace_id": workspace_id, **dict(zip(columns, row))} for row in results
                    ]
                    logger.info(
                        "listed_jobs_for_workspace_from_delta",
                        workspace_id=workspace_id,
                        count=len(jobs),
                        table=table,
                    )
                    return jobs
        except Exception as e:
            logger.error(
                "list_jobs_for_workspace_error",
                error=str(e),
                workspace_id=workspace_id,
                table=table,
            )
            raise

    def list_job_runs(
        self, workspace_id: str, job_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """List distinct job runs for a job in a workspace within the date range."""
        if not self._metrics_table:
            logger.warning(
                "databricks_list_job_runs_table_not_set",
                message="DATABRICKS_JOB_CLUSTER_METRICS_TABLE is required.",
            )
            return []

        table = self._metrics_table
        query = f"""
        SELECT
          CAST(cluster_id AS STRING) AS cluster_id,
          MAX(job_run_date) AS job_run_date,
          COALESCE(MAX(job_run_duration_seconds), 0.0) AS job_run_duration_seconds,
          COALESCE(MAX(azure_driver_vm_size), MAX(azure_worker_vm_size)) AS azure_driver_vm_size,
          CAST(COALESCE(MAX(driver_node_count), 1) AS BIGINT) AS driver_node_count,
          COALESCE(AVG(avg_driver_cpu_utilization_pct), 0.0) AS avg_driver_cpu_utilization_pct,
          COALESCE(AVG(avg_driver_memory_utilization_pct), 0.0) AS avg_driver_memory_utilization_pct,
          COALESCE(MAX(peak_driver_cpu_utilization_pct), 0.0) AS peak_driver_cpu_utilization_pct,
          COALESCE(AVG(avg_worker_cpu_utilization_pct), 0.0) AS avg_worker_cpu_utilization_pct,
          COALESCE(AVG(avg_worker_memory_utilization_pct), 0.0) AS avg_worker_memory_utilization_pct,
          COALESCE(AVG(avg_worker_nodes_consumed), 0.0) AS avg_worker_nodes_consumed,
          COALESCE(MAX(total_worker_vcpus_provisioned), 0.0) AS total_worker_vcpus_provisioned,
          COALESCE(MAX(total_worker_memory_gb_provisioned), 0.0) AS total_worker_memory_gb_provisioned,
          COALESCE(MAX(peak_worker_cpu_utilization_pct), 0.0) AS peak_worker_cpu_utilization_pct,
          COALESCE(MAX(peak_worker_memory_utilization_pct), 0.0) AS peak_worker_memory_utilization_pct,
          COALESCE(MAX(azure_worker_vm_size), 'Standard_E8s_v3') AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          MAX(job_type) AS job_type
        FROM {table}
        WHERE workspace_id = ?
          AND job_id = ?
          AND job_run_date >= ?
          AND job_run_date <= ?
          AND cluster_id IS NOT NULL
        GROUP BY cluster_id
        ORDER BY job_run_date DESC, cluster_id DESC
        """
        params: List[Any] = [workspace_id, job_id, start_date, end_date]
        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(
                "list_job_runs_error",
                error=str(e),
                workspace_id=workspace_id,
                job_id=job_id,
                table=table,
            )
            raise

    def get_job_metrics(
        self, workspace_id: str, job_id: str, start_date: str, end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get aggregated metrics for one job in a workspace."""
        if not self._metrics_table:
            logger.warning(
                "databricks_job_cluster_metrics_table_not_set",
                message="DATABRICKS_JOB_CLUSTER_METRICS_TABLE is required; returning no metrics.",
            )
            return None

        table = self._metrics_table
        query = f"""
        SELECT
          COALESCE(AVG(job_run_duration_seconds), 0.0) AS avg_job_run_duration_seconds,
          COALESCE(MAX(azure_driver_vm_size), MAX(azure_worker_vm_size)) AS azure_driver_vm_size,
          CAST(COALESCE(MAX(driver_node_count), 1) AS BIGINT) AS driver_node_count,
          COALESCE(AVG(avg_driver_cpu_utilization_pct), 0.0) AS avg_driver_cpu_utilization_pct,
          COALESCE(AVG(avg_driver_memory_utilization_pct), 0.0) AS avg_driver_memory_utilization_pct,
          COALESCE(MAX(peak_driver_cpu_utilization_pct), 0.0) AS peak_driver_cpu_utilization_pct,
          COALESCE(AVG(driver_vcpus_consumed), 0.0) AS avg_driver_vcpus_consumed,
          COALESCE(AVG(driver_memory_gb_consumed), 0.0) AS avg_driver_memory_gb_consumed,
          COALESCE(AVG(avg_worker_cpu_utilization_pct), 0.0) AS avg_worker_cpu_utilization_pct,
          COALESCE(AVG(avg_worker_memory_utilization_pct), 0.0) AS avg_worker_memory_utilization_pct,
          COALESCE(MAX(peak_worker_cpu_utilization_pct), 0.0) AS peak_worker_cpu_utilization_pct,
          COALESCE(MAX(peak_worker_memory_utilization_pct), 0.0) AS peak_worker_memory_utilization_pct,
          COALESCE(AVG(avg_worker_nodes_consumed), 0.0) AS avg_worker_nodes_consumed,
          COALESCE(percentile_approx(avg_worker_nodes_consumed, 0.95), 0.0) AS p95_worker_nodes_consumed,
          COALESCE(AVG(total_worker_vcpus_provisioned), 0.0) AS avg_total_worker_vcpus_provisioned,
          COALESCE(AVG(total_worker_memory_gb_provisioned), 0.0) AS avg_total_worker_memory_gb_provisioned,
          COALESCE(percentile_approx(p99_worker_nodes_consumed, 0.99), 0.0) AS p99_worker_nodes_consumed,
          COUNT(*) AS total_runs,
          COALESCE(MAX(azure_worker_vm_size), 'Standard_E8s_v3') AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          MAX(job_run_date) AS last_job_run_date,
          MAX(job_name) AS job_name,
          MAX(workspace_name) AS workspace_name,
          MAX(job_run_start_time_utc) AS job_run_start_time_utc,
          MAX(job_run_end_time_utc) AS job_run_end_time_utc,
          MAX(delta_tables_ingested) AS delta_tables_ingested,
          MAX({DELTA_WORKER_NODE_PROVISIONING_EFFICIENCY_SQL_EXPR}) AS worker_node_provisioning_efficiency_pct,
          MAX(worker_cpu_utilization_efficiency_pct) AS worker_cpu_utilization_efficiency_pct,
          MAX({DELTA_MEMORY_EFFICIENCY_SQL_EXPR}) AS worker_memory_utilization_efficency_pct,
          MAX(job_type) AS job_type,
          MAX(processed_row_count) AS processed_row_count,
          MAX(processed_bytes) AS processed_bytes
        FROM {table}
        WHERE workspace_id = ?
          AND job_id = ?
          AND job_run_date >= ?
          AND job_run_date <= ?
        """
        params: List[Any] = [workspace_id, job_id, start_date, end_date]
        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    if not row:
                        return None
                    columns = [desc[0] for desc in cursor.description]
                    rec = dict(zip(columns, row))
                    total_runs = int(rec.get("total_runs") or 0)
                    if total_runs == 0:
                        return None
                    return rec
        except Exception as e:
            logger.error(
                "get_job_metrics_error",
                error=str(e),
                workspace_id=workspace_id,
                job_id=job_id,
                table=table,
            )
            raise

    def collect_cost_data(
        self, start_date: str, end_date: str, job_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """Collect cost and usage data."""
        logger.info("collecting_cost_data", start_date=start_date, end_date=end_date)
        return []
