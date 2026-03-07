"""Databricks data collector: reads pre-aggregated job metrics from a centralized Delta table."""
from databricks import sql
from typing import List, Optional, Dict, Any
from shared.config.settings import settings
from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _delta_row_to_job_cluster_metrics(row: Dict[str, Any]) -> JobClusterMetrics:
    """Map a centralized Delta table row to JobClusterMetrics."""
    delta_tables = row.get("delta_tables")
    if isinstance(delta_tables, str):
        try:
            import json
            delta_tables = json.loads(delta_tables) if delta_tables else []
        except Exception:
            delta_tables = []
    elif not isinstance(delta_tables, list):
        delta_tables = [] if delta_tables is None else []

    num_tables = len(delta_tables) if delta_tables else None
    max_nodes = row.get("max_nodes_provisioned")
    if max_nodes is not None and not isinstance(max_nodes, int):
        try:
            max_nodes = int(max_nodes)
        except (TypeError, ValueError):
            max_nodes = 16

    return JobClusterMetrics(
        date=str(row.get("job_date", row.get("date", ""))),
        workspace_id=str(row.get("workspace_id", "")),
        job_id=str(row.get("job_id", "")),
        job_run_id=str(row.get("cluster_id", row.get("job_run_id", ""))),
        job_duration_seconds=float(row.get("duration", row.get("job_duration_seconds", 0))),
        task_count=int(row.get("task_count", 0)),
        parallelism_ratio=float(row.get("parallelism_ratio", 1.0)),
        avg_cpu_utilization_pct=float(row.get("cpu_utilization_pct", row.get("avg_cpu_utilization_pct", 0))),
        avg_memory_utilization_pct=float(row.get("memory_utilization_pct", row.get("avg_memory_utilization_pct", 0))),
        peak_cpu_utilization_pct=float(row.get("peak_cpu_utilization_pct", 0)),
        peak_memory_utilization_pct=float(row.get("peak_memory_utilization_pct", 0)),
        avg_nodes_consumed=float(row.get("avg_nodes_consumed", 0)),
        p95_nodes_consumed=float(row.get("p95_nodes_consumed", 0)),
        p99_nodes_consumed=float(row.get("p99_nodes_consumed", 0)),
        total_cost_usd=float(row.get("total_cost_usd", 0)),
        cost_per_hour_usd=float(row.get("cost_per_hour_usd", 0)),
        rows_added=row.get("rows_added"),
        num_of_tables=num_tables,
        workload_type=row.get("job_type", row.get("workload_type")),
        current_node_type=str(row.get("node_type", row.get("current_node_type", "Standard_E8s_v3"))),
        current_min_workers=int(row.get("current_min_workers", 1)),
        current_max_workers=int(max_nodes) if max_nodes is not None else int(row.get("current_max_workers", 16)),
        job_date=str(row["job_date"]) if row.get("job_date") is not None else None,
        workspace_name=row.get("workspace_name"),
        job_name=row.get("job_name"),
        cluster_id=str(row["cluster_id"]) if row.get("cluster_id") is not None else None,
        start_time=str(row["start_time"]) if row.get("start_time") is not None else None,
        end_time=str(row["end_time"]) if row.get("end_time") is not None else None,
        delta_tables=delta_tables if delta_tables else None,
        provisioning_efficiency_pct=_opt_float(row, "provisioning_efficiency_pct"),
        cpu_utilization_efficiency_pct=_opt_float(row, "cpu_utilization_efficiency_pct"),
        memory_utilization_efficiency_pct=_opt_float(row, "memory_utilization_efficiency_pct"),
        max_nodes_provisioned=_opt_int(row, "max_nodes_provisioned"),
        total_cpus_provisioned=_opt_int(row, "total_cpus_provisioned"),
        total_memory_gb_provisioned=_opt_float(row, "total_memory_gb_provisioned"),
    )


def _opt_float(row: Dict[str, Any], key: str) -> Optional[float]:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_int(row: Dict[str, Any], key: str) -> Optional[int]:
    v = row.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


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
        workspace_id: Optional[str] = None
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
        query = f"SELECT * FROM {table} WHERE {where} ORDER BY job_date DESC, start_time DESC LIMIT 1000"

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
                            metrics.append(_delta_row_to_job_cluster_metrics(row_dict))
                        except Exception as e:
                            logger.warning("failed_to_parse_delta_row", error=str(e), row=row_dict)
                    logger.info("collected_job_cluster_metrics_from_delta", count=len(metrics), table=table)
                    return metrics
        except Exception as e:
            logger.error("databricks_collection_error", error=str(e), table=table)
            raise

    def collect_cost_data(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """Collect cost and usage data."""
        logger.info("collecting_cost_data", start_date=start_date, end_date=end_date)
        return []
