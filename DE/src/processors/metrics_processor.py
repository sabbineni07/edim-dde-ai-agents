"""Metrics processing and aggregation."""
from typing import List, Dict, Any
from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger
import pandas as pd

logger = get_logger(__name__)

# Optional Delta table fields to pass through to the agent (from centralized table)
_OPTIONAL_DELTA_KEYS = (
    "job_name", "workspace_name", "job_date", "cluster_id", "start_time", "end_time",
    "delta_tables", "provisioning_efficiency_pct", "cpu_utilization_efficiency_pct",
    "memory_utilization_efficiency_pct", "max_nodes_provisioned", "total_cpus_provisioned",
    "total_memory_gb_provisioned", "workload_type",
)


class MetricsProcessor:
    """Process and aggregate job metrics."""

    def aggregate_by_job(self, metrics: List[JobClusterMetrics]) -> Dict[str, Dict]:
        """Aggregate metrics by job_id.
        Passes through optional Delta table fields (job_name, delta_tables, efficiency %, etc.)
        from the first record per job so agents can use them.
        """
        if not metrics:
            return {}

        raw = [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in metrics]
        df = pd.DataFrame(raw)

        aggregated = {}
        for job_id in df["job_id"].unique():
            job_df = df[df["job_id"] == job_id]
            first = job_df.iloc[0]

            agg: Dict[str, Any] = {
                "avg_duration_seconds": job_df["job_duration_seconds"].mean(),
                "avg_cost_usd": job_df["total_cost_usd"].mean(),
                "avg_cpu_utilization": job_df["avg_cpu_utilization_pct"].mean(),
                "avg_memory_utilization": job_df["avg_memory_utilization_pct"].mean(),
                "peak_cpu_utilization": job_df["peak_cpu_utilization_pct"].max(),
                "peak_memory_utilization": job_df["peak_memory_utilization_pct"].max(),
                "peak_cpu_utilization_pct": float(job_df["peak_cpu_utilization_pct"].max()),
                "peak_memory_utilization_pct": float(job_df["peak_memory_utilization_pct"].max()),
                "avg_nodes_consumed": float(job_df["avg_nodes_consumed"].mean()),
                "p95_nodes_consumed": job_df["p95_nodes_consumed"].quantile(0.95),
                "p99_nodes_consumed": job_df["p99_nodes_consumed"].quantile(0.99),
                "total_runs": len(job_df),
                "current_node_type": first["current_node_type"],
                "current_min_workers": int(first["current_min_workers"]),
                "current_max_workers": int(first["current_max_workers"]),
            }
            # Pass through optional Delta fields for the agent
            for key in _OPTIONAL_DELTA_KEYS:
                if key in first and first[key] is not None:
                    agg[key] = first[key]
            aggregated[job_id] = agg

        logger.info("aggregated_metrics", job_count=len(aggregated))
        return aggregated
    
    def identify_workload_pattern(self, metrics: JobClusterMetrics) -> str:
        """Identify workload pattern from metrics.
        
        Args:
            metrics: JobClusterMetrics object
            
        Returns:
            Workload type string
        """
        # Simple pattern identification logic
        if metrics.rows_added and metrics.rows_added > 10000000:
            if metrics.num_of_tables and metrics.num_of_tables <= 3:
                return "Large_ETL"
            return "Complex_ETL"
        
        if metrics.avg_cpu_utilization_pct > 70:
            return "CPU_Intensive"
        
        if metrics.avg_memory_utilization_pct > 70:
            return "Memory_Intensive"
        
        return "Balanced"

