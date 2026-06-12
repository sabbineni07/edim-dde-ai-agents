"""Metrics processing and aggregation."""

from typing import Any, Dict, List

import pandas as pd

from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_OPTIONAL_DELTA_KEYS = (
    "job_name",
    "workspace_name",
    "job_run_start_time_utc",
    "job_run_end_time_utc",
    "delta_tables_ingested",
    "worker_node_provisioning_efficency_pct",
    "worker_cpu_utilization_efficiency_pct",
    "worker_memory_utilization_efficency_pct",
    "total_worker_vcpus_provisioned",
    "total_worker_memory_gb_provisioned",
    "avg_worker_vcpus_consumed",
    "avg_worker_memory_gb_consumed",
    "job_type",
    "processed_row_count",
    "processed_bytes",
)


class MetricsProcessor:
    """Process and aggregate job metrics."""

    def aggregate_by_job(self, metrics: List[JobClusterMetrics]) -> Dict[str, Dict]:
        """Aggregate metrics by job_id."""
        if not metrics:
            return {}

        raw = [m.model_dump() for m in metrics]
        df = pd.DataFrame(raw)

        aggregated = {}
        for job_id in df["job_id"].unique():
            job_df = df[df["job_id"] == job_id]
            first = job_df.iloc[0]
            last_run_date = None
            if "job_run_date" in job_df.columns:
                try:
                    last_run_date = max(job_df["job_run_date"])
                except Exception:
                    last_run_date = None

            agg: Dict[str, Any] = {
                "avg_job_run_duration_seconds": job_df["job_run_duration_seconds"].mean(),
                "avg_worker_cpu_utilization_pct": job_df["avg_worker_cpu_utilization_pct"].mean(),
                "avg_worker_memory_utilization_pct": job_df[
                    "avg_worker_memory_utilization_pct"
                ].mean(),
                "peak_worker_cpu_utilization_pct": float(
                    job_df["peak_worker_cpu_utilization_pct"].max()
                ),
                "peak_worker_memory_utilization_pct": float(
                    job_df["peak_worker_memory_utilization_pct"].max()
                ),
                "avg_worker_nodes_consumed": float(job_df["avg_worker_nodes_consumed"].mean()),
                "p95_worker_nodes_consumed": float(
                    job_df["avg_worker_nodes_consumed"].quantile(0.95)
                ),
                "p99_worker_nodes_consumed": float(
                    job_df["p99_worker_nodes_consumed"].quantile(0.99)
                ),
                "total_runs": len(job_df),
                "azure_worker_vm_size": first["azure_worker_vm_size"],
                "max_worker_nodes_provisioned": int(first["max_worker_nodes_provisioned"]),
                "last_job_run_date": last_run_date,
            }
            for key in _OPTIONAL_DELTA_KEYS:
                if key in first and first[key] is not None:
                    agg[key] = first[key]
            aggregated[job_id] = agg

        logger.info("aggregated_metrics", job_count=len(aggregated))
        return aggregated

    def identify_workload_pattern(self, metrics: JobClusterMetrics) -> str:
        """Identify workload pattern from metrics."""
        if metrics.processed_row_count and metrics.processed_row_count > 10000000:
            if metrics.delta_tables_ingested and metrics.delta_tables_ingested <= 3:
                return "Large_ETL"
            return "Complex_ETL"

        if metrics.avg_worker_cpu_utilization_pct > 70:
            return "CPU_Intensive"

        if metrics.avg_worker_memory_utilization_pct > 70:
            return "Memory_Intensive"

        return "Balanced"
