"""Databricks data collector: reads pre-aggregated job metrics from a centralized Delta table."""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from databricks import sql

from shared.config.settings import settings
from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_sql_value(value: Any) -> Any:
    """Coerce Databricks SQL driver values to JSON-friendly primitives."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows_to_dicts(columns: List[str], rows: List[Any]) -> List[Dict[str, Any]]:
    return [{col: _normalize_sql_value(val) for col, val in zip(columns, row)} for row in rows]


_METRICS_SELECT_BODY = """
  CAST(job_run_date AS STRING) AS job_run_date,
  CAST(workspace_id AS STRING) AS workspace_id,
  workspace_name,
  CAST(job_id AS STRING) AS job_id,
  {job_run_id_select},
  CAST(cluster_id AS STRING) AS cluster_id,
  job_type,
  job_name,
  dbr_version,
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
  CAST(worker_node_provisioning_efficiency_pct AS DOUBLE) AS worker_node_provisioning_efficiency_pct,
  CAST(worker_cpu_utilization_efficiency_pct AS DOUBLE) AS worker_cpu_utilization_efficiency_pct,
  CAST(worker_memory_utilization_efficiency_pct AS DOUBLE) AS worker_memory_utilization_efficiency_pct,
  CAST(array_size(delta_tables_ingested) AS BIGINT) AS delta_tables_ingested,
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
        from shared.databricks.sql_config import normalize_databricks_sql_config

        sql_cfg = normalize_databricks_sql_config(
            {
                "databricks_server_hostname": server_hostname
                or settings.databricks_server_hostname,
                "databricks_http_path": http_path or settings.databricks_http_path,
            },
            databricks_host=settings.databricks_host,
        )
        self._metrics_table = (
            metrics_table or settings.databricks_job_cluster_metrics_table or ""
        ).strip() or None
        self._server_hostname = sql_cfg["databricks_server_hostname"]
        self._http_path = sql_cfg["databricks_http_path"]
        self._table_columns: Optional[set[str]] = None

    def _fetch_table_columns(self) -> set[str]:
        """Load and cache Delta table column names (lowercase)."""
        if self._table_columns is not None:
            return self._table_columns
        table = self._metrics_table
        if not table:
            self._table_columns = set()
            return self._table_columns
        try:
            with sql.connect(**self._connection_params()) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(f"DESCRIBE TABLE {table}")
                    rows = cursor.fetchall()
                    self._table_columns = {
                        str(row[0]).strip().lower()
                        for row in rows
                        if row and row[0] and not str(row[0]).startswith("#")
                    }
                    logger.debug(
                        "databricks_table_columns_loaded",
                        table=table,
                        column_count=len(self._table_columns),
                        has_job_run_id="job_run_id" in self._table_columns,
                    )
        except Exception as e:
            logger.warning(
                "databricks_describe_table_failed",
                error=str(e),
                table=table,
                hint="Assuming job_run_id column is absent.",
            )
            self._table_columns = set()
        return self._table_columns

    def _has_job_run_id_column(self) -> bool:
        return "job_run_id" in self._fetch_table_columns()

    def _job_run_id_select(self, *, aggregate_max: bool = False) -> str:
        if self._has_job_run_id_column():
            source = "MAX(job_run_id)" if aggregate_max else "job_run_id"
            return f"CAST({source} AS STRING) AS job_run_id"
        if not aggregate_max:
            logger.info(
                "databricks_job_run_id_column_missing",
                table=self._metrics_table,
                message="Returning NULL job_run_id until Delta table is migrated.",
            )
        return "CAST(NULL AS STRING) AS job_run_id"

    def _metrics_select(self) -> str:
        return "SELECT\n" + _METRICS_SELECT_BODY.format(job_run_id_select=self._job_run_id_select())

    def _connection_params(self) -> Dict[str, Any]:
        """Build SQL connector params; token from request user OAuth, app SP, env, or Azure AD."""
        from shared.auth.databricks_tokens import resolve_databricks_sql_access_token

        if not (self._server_hostname and self._http_path):
            raise RuntimeError(
                "Databricks SQL connection is not configured "
                f"(hostname={self._server_hostname!r}, http_path={self._http_path!r})."
            )

        token = resolve_databricks_sql_access_token()
        if not token:
            raise RuntimeError(
                "No Databricks SQL access token available. On Databricks Apps, attach a "
                "sql-warehouse resource; locally use az login or DATABRICKS_TOKEN."
            )
        if token and not (settings.databricks_token or "").strip():
            logger.debug(
                "databricks_sql_token_resolved",
                source="request_or_runtime",
            )
        return {
            "server_hostname": self._server_hostname,
            "http_path": self._http_path,
            "access_token": token,
            # Allow SQL warehouse auto-srat (cold boot can take several minutes).
            "_socket_timeout": 300,
            "_query_timeout": 0,
        }

    def collect_job_cluster_metrics(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
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
            start_date, end_date, job_ids, workspace_id, cluster_id, job_run_id
        )

    def _collect_from_delta_table(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Fetch records from centralized Delta table by job_id and optional date range."""
        table = self._metrics_table
        run_only = bool(
            (cluster_id and str(cluster_id).strip()) or (job_run_id and str(job_run_id).strip())
        ) and not (start_date and end_date)
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
        if cluster_id:
            conditions.append("CAST(cluster_id AS STRING) = ?")
            params.append(str(cluster_id))
        elif job_run_id:
            if self._has_job_run_id_column():
                conditions.append("CAST(job_run_id AS STRING) = ?")
                params.append(str(job_run_id))
            else:
                logger.warning(
                    "databricks_job_run_id_filter_unavailable",
                    job_run_id=job_run_id,
                    table=table,
                )
                return []
        if not conditions:
            logger.warning("databricks_collect_metrics_no_filters")
            return []
        where = " AND ".join(conditions)
        query = f"""
        {self._metrics_select()}
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
                        row_dict = _rows_to_dicts(columns, [row])[0]
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
                    workspaces = _rows_to_dicts(columns, results)
                    logger.info("listed_workspaces_from_delta", count=len(workspaces), table=table)
                    return workspaces
        except Exception as e:
            logger.error(
                "list_workspaces_error",
                error=str(e),
                error_type=type(e).__name__,
                table=table,
                server_hostname=self._server_hostname,
                http_path=self._http_path,
            )
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
          AVG(avg_worker_cpu_utilization_pct) AS avg_worker_cpu_utilization_pct,
          AVG(avg_worker_memory_utilization_pct) AS avg_worker_memory_utilization_pct,
          CAST(COUNT(*) AS BIGINT) AS total_runs,
          COALESCE(AVG(job_run_duration_seconds), 0.0) AS avg_job_run_duration_seconds,
          COALESCE(MAX(azure_driver_vm_size), MAX(azure_worker_vm_size)) AS azure_driver_vm_size,
          MAX(azure_worker_vm_size) AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          CAST(MAX(job_run_date) AS STRING) AS last_job_run_date,
          MAX(dbr_version) AS dbr_version
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
                        {"workspace_id": workspace_id, **row}
                        for row in _rows_to_dicts(columns, results)
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
        job_run_id_select = self._job_run_id_select(aggregate_max=True)
        query = f"""
        SELECT
          CAST(cluster_id AS STRING) AS cluster_id,
          {job_run_id_select},
          CAST(MAX(job_run_date) AS STRING) AS job_run_date,
          COALESCE(MAX(job_run_duration_seconds), 0.0) AS job_run_duration_seconds,
          COALESCE(MAX(azure_driver_vm_size), MAX(azure_worker_vm_size)) AS azure_driver_vm_size,
          CAST(COALESCE(MAX(driver_node_count), 1) AS BIGINT) AS driver_node_count,
          COALESCE(AVG(avg_driver_cpu_utilization_pct), 0.0) AS avg_driver_cpu_utilization_pct,
          COALESCE(AVG(avg_driver_memory_utilization_pct), 0.0) AS avg_driver_memory_utilization_pct,
          COALESCE(MAX(peak_driver_cpu_utilization_pct), 0.0) AS peak_driver_cpu_utilization_pct,
          AVG(avg_worker_cpu_utilization_pct) AS avg_worker_cpu_utilization_pct,
          AVG(avg_worker_memory_utilization_pct) AS avg_worker_memory_utilization_pct,
          AVG(avg_worker_nodes_consumed) AS avg_worker_nodes_consumed,
          MAX(total_worker_vcpus_provisioned) AS total_worker_vcpus_provisioned,
          MAX(total_worker_memory_gb_provisioned) AS total_worker_memory_gb_provisioned,
          MAX(peak_worker_cpu_utilization_pct) AS peak_worker_cpu_utilization_pct,
          MAX(peak_worker_memory_utilization_pct) AS peak_worker_memory_utilization_pct,
          MAX(azure_worker_vm_size) AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          MAX(job_type) AS job_type,
          MAX(dbr_version) AS dbr_version
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
                    return _rows_to_dicts(columns, cursor.fetchall())
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
          AVG(avg_worker_cpu_utilization_pct) AS avg_worker_cpu_utilization_pct,
          AVG(avg_worker_memory_utilization_pct) AS avg_worker_memory_utilization_pct,
          MAX(peak_worker_cpu_utilization_pct) AS peak_worker_cpu_utilization_pct,
          MAX(peak_worker_memory_utilization_pct) AS peak_worker_memory_utilization_pct,
          AVG(avg_worker_nodes_consumed) AS avg_worker_nodes_consumed,
          percentile_approx(avg_worker_nodes_consumed, 0.95) AS p95_worker_nodes_consumed,
          AVG(total_worker_vcpus_provisioned) AS avg_total_worker_vcpus_provisioned,
          AVG(total_worker_memory_gb_provisioned) AS avg_total_worker_memory_gb_provisioned,
          percentile_approx(p99_worker_nodes_consumed, 0.99) AS p99_worker_nodes_consumed,
          COUNT(*) AS total_runs,
          MAX(azure_worker_vm_size) AS azure_worker_vm_size,
          CAST(COALESCE(MAX(max_worker_nodes_provisioned), 1) AS BIGINT) AS max_worker_nodes_provisioned,
          CAST(MAX(job_run_date) AS STRING) AS last_job_run_date,
          MAX(job_name) AS job_name,
          MAX(dbr_version) AS dbr_version,
          MAX(workspace_name) AS workspace_name,
          MAX(job_run_start_time_utc) AS job_run_start_time_utc,
          MAX(job_run_end_time_utc) AS job_run_end_time_utc,
          MAX(delta_tables_ingested) AS delta_tables_ingested,
          MAX(worker_node_provisioning_efficiency_pct) AS worker_node_provisioning_efficiency_pct,
          MAX(worker_cpu_utilization_efficiency_pct) AS worker_cpu_utilization_efficiency_pct,
          MAX(worker_memory_utilization_efficiency_pct) AS worker_memory_utilization_efficiency_pct,
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
                    rec = _rows_to_dicts(columns, [row])[0]
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
