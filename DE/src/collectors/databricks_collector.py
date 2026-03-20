"""Databricks data collector: reads pre-aggregated job metrics from a centralized Delta table."""

from typing import Any, Dict, List, Optional

from databricks import sql

from shared.config.settings import settings
from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class DatabricksCollector:
    """Collects job metrics from a pre-aggregated centralized Delta table only."""

    def __init__(self):
        self.connection_params = {
            "server_hostname": settings.databricks_server_hostname,
            "http_path": settings.databricks_http_path,
            "access_token": settings.databricks_token,
        }
        self._metrics_table = (settings.databricks_job_cluster_metrics_table or "").strip() or None

    def collect_job_cluster_metrics(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
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
        return self._collect_from_delta_table(start_date, end_date, job_ids, workspace_id)

    def _collect_from_delta_table(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Fetch records from centralized Delta table by job_id and date range."""
        table = self._metrics_table
        # Parameterized: job_date >= start_date AND job_date <= end_date [AND job_id IN (...)] [AND workspace_id = ?]
        conditions = ["job_date >= ?", "job_date <= ?"]
        params: List[Any] = [start_date, end_date]
        if job_ids:
            placeholders = ", ".join(["?" for _ in job_ids])
            conditions.append(f"job_id IN ({placeholders})")
            params.extend(job_ids)
        if workspace_id:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        where = " AND ".join(conditions)
        query = f"""
        SELECT
          CAST(COALESCE(job_date, date) AS STRING) AS date,
          CAST(workspace_id AS STRING) AS workspace_id,
          CAST(job_id AS STRING) AS job_id,
          CAST(COALESCE(cluster_id, job_run_id) AS STRING) AS job_run_id,
          COALESCE(CAST(duration AS DOUBLE), CAST(job_duration_seconds AS DOUBLE), 0.0) AS job_duration_seconds,
          CAST(COALESCE(task_count, 0) AS BIGINT) AS task_count,
          COALESCE(CAST(parallelism_ratio AS DOUBLE), 1.0) AS parallelism_ratio,
          COALESCE(CAST(cpu_utilization_pct AS DOUBLE), CAST(avg_cpu_utilization_pct AS DOUBLE), 0.0) AS avg_cpu_utilization_pct,
          COALESCE(CAST(memory_utilization_pct AS DOUBLE), CAST(avg_memory_utilization_pct AS DOUBLE), 0.0) AS avg_memory_utilization_pct,
          COALESCE(CAST(peak_cpu_utilization_pct AS DOUBLE), 0.0) AS peak_cpu_utilization_pct,
          COALESCE(CAST(peak_memory_utilization_pct AS DOUBLE), 0.0) AS peak_memory_utilization_pct,
          COALESCE(CAST(avg_nodes_consumed AS DOUBLE), 0.0) AS avg_nodes_consumed,
          COALESCE(CAST(p95_nodes_consumed AS DOUBLE), 0.0) AS p95_nodes_consumed,
          COALESCE(CAST(p99_nodes_consumed AS DOUBLE), 0.0) AS p99_nodes_consumed,
          COALESCE(CAST(total_cost_usd AS DOUBLE), 0.0) AS total_cost_usd,
          COALESCE(CAST(cost_per_hour_usd AS DOUBLE), 0.0) AS cost_per_hour_usd,
          CAST(rows_added AS BIGINT) AS rows_added,
          CAST(num_of_tables AS BIGINT) AS num_of_tables,
          COALESCE(workload_type, job_type) AS workload_type,
          COALESCE(current_node_type, node_type, 'Standard_E8s_v3') AS current_node_type,
          CAST(COALESCE(current_min_workers, 1) AS BIGINT) AS current_min_workers,
          CAST(COALESCE(max_nodes_provisioned, current_max_workers, 16) AS BIGINT) AS current_max_workers,
          CAST(job_date AS STRING) AS job_date,
          workspace_name,
          job_name,
          CAST(cluster_id AS STRING) AS cluster_id,
          CAST(start_time AS STRING) AS start_time,
          CAST(end_time AS STRING) AS end_time,
          CAST(NULL AS ARRAY<STRING>) AS delta_tables,
          CAST(provisioning_efficiency_pct AS DOUBLE) AS provisioning_efficiency_pct,
          CAST(cpu_utilization_efficiency_pct AS DOUBLE) AS cpu_utilization_efficiency_pct,
          CAST(memory_utilization_efficiency_pct AS DOUBLE) AS memory_utilization_efficiency_pct,
          CAST(max_nodes_provisioned AS BIGINT) AS max_nodes_provisioned,
          CAST(total_cpus_provisioned AS BIGINT) AS total_cpus_provisioned,
          CAST(total_memory_gb_provisioned AS DOUBLE) AS total_memory_gb_provisioned
        FROM {table}
        WHERE {where}
        ORDER BY job_date DESC, start_time DESC
        LIMIT 1000
        """

        try:
            with sql.connect(**self.connection_params) as conn:
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

    def list_workspaces(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
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
          CAST(MIN(job_date) AS STRING) AS first_seen_date,
          CAST(MAX(job_date) AS STRING) AS last_seen_date
        FROM {table}
        WHERE job_date >= ?
          AND job_date <= ?
        GROUP BY workspace_id
        ORDER BY last_seen_date DESC, workspace_id
        """
        params: List[Any] = [start_date, end_date]

        try:
            with sql.connect(**self.connection_params) as conn:
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
          COALESCE(MAX(workload_type), MAX(job_type)) AS workload_type,
          COALESCE(AVG(COALESCE(cpu_utilization_pct, avg_cpu_utilization_pct)), 0.0) AS avg_cpu_utilization_pct,
          COALESCE(AVG(COALESCE(memory_utilization_pct, avg_memory_utilization_pct)), 0.0) AS avg_memory_utilization_pct,
          CAST(COUNT(*) AS BIGINT) AS total_runs,
          COALESCE(AVG(COALESCE(duration, job_duration_seconds)), 0.0) AS avg_duration_seconds,
          COALESCE(MAX(current_node_type), MAX(node_type), 'Standard_E8s_v3') AS current_node_type,
          CAST(COALESCE(MAX(COALESCE(current_min_workers, 1)), 1) AS BIGINT) AS current_min_workers,
          CAST(COALESCE(MAX(COALESCE(max_nodes_provisioned, current_max_workers, 16)), 16) AS BIGINT) AS current_max_workers,
          CAST(MAX(job_date) AS STRING) AS last_run_date
        FROM {table}
        WHERE workspace_id = ?
          AND job_date >= ?
          AND job_date <= ?
        GROUP BY job_id
        ORDER BY job_name, job_id
        """
        params: List[Any] = [workspace_id, start_date, end_date]

        try:
            with sql.connect(**self.connection_params) as conn:
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
          COALESCE(AVG(COALESCE(duration, job_duration_seconds)), 0.0) AS avg_duration_seconds,
          COALESCE(AVG(total_cost_usd), 0.0) AS avg_cost_usd,
          COALESCE(AVG(COALESCE(cpu_utilization_pct, avg_cpu_utilization_pct)), 0.0) AS avg_cpu_utilization,
          COALESCE(AVG(COALESCE(memory_utilization_pct, avg_memory_utilization_pct)), 0.0) AS avg_memory_utilization,
          COALESCE(MAX(peak_cpu_utilization_pct), 0.0) AS peak_cpu_utilization,
          COALESCE(MAX(peak_memory_utilization_pct), 0.0) AS peak_memory_utilization,
          COALESCE(MAX(peak_cpu_utilization_pct), 0.0) AS peak_cpu_utilization_pct,
          COALESCE(MAX(peak_memory_utilization_pct), 0.0) AS peak_memory_utilization_pct,
          COALESCE(AVG(avg_nodes_consumed), 0.0) AS avg_nodes_consumed,
          COALESCE(percentile_approx(p95_nodes_consumed, 0.95), 0.0) AS p95_nodes_consumed,
          COALESCE(percentile_approx(p99_nodes_consumed, 0.99), 0.0) AS p99_nodes_consumed,
          COUNT(*) AS total_runs,
          COALESCE(MAX(current_node_type), MAX(node_type), 'Standard_E8s_v3') AS current_node_type,
          CAST(COALESCE(MAX(COALESCE(current_min_workers, 1)), 1) AS BIGINT) AS current_min_workers,
          CAST(COALESCE(MAX(COALESCE(max_nodes_provisioned, current_max_workers, 16)), 16) AS BIGINT) AS current_max_workers,
          MAX(job_date) AS last_run_date,
          MAX(job_name) AS job_name,
          MAX(workspace_name) AS workspace_name,
          MAX(job_date) AS job_date,
          MAX(cluster_id) AS cluster_id,
          MAX(start_time) AS start_time,
          MAX(end_time) AS end_time,
          MAX(delta_tables) AS delta_tables,
          MAX(provisioning_efficiency_pct) AS provisioning_efficiency_pct,
          MAX(cpu_utilization_efficiency_pct) AS cpu_utilization_efficiency_pct,
          MAX(memory_utilization_efficiency_pct) AS memory_utilization_efficiency_pct,
          CAST(MAX(max_nodes_provisioned) AS BIGINT) AS max_nodes_provisioned,
          CAST(MAX(total_cpus_provisioned) AS BIGINT) AS total_cpus_provisioned,
          MAX(total_memory_gb_provisioned) AS total_memory_gb_provisioned,
          COALESCE(MAX(workload_type), MAX(job_type)) AS workload_type
        FROM {table}
        WHERE workspace_id = ?
          AND job_id = ?
          AND job_date >= ?
          AND job_date <= ?
        """
        params: List[Any] = [workspace_id, job_id, start_date, end_date]
        try:
            with sql.connect(**self.connection_params) as conn:
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
