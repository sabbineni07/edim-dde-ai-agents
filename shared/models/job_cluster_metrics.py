"""Job cluster metrics data model — aligned with Databricks Delta table schema."""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict

# Canonical Delta table column names (Unity Catalog: *.dde_metrics.job_cluster_metrics)
DELTA_TABLE_COLUMNS: List[str] = [
    "job_run_date",
    "workspace_id",
    "workspace_name",
    "cluster_id",
    "job_id",
    "job_type",
    "job_name",
    "job_run_start_time_utc",
    "job_run_end_time_utc",
    "job_run_duration_seconds",
    "azure_driver_vm_size",
    "driver_node_count",
    "driver_vcpus_consumed",
    "driver_memory_gb_consumed",
    "avg_driver_cpu_utilization_pct",
    "avg_driver_memory_utilization_pct",
    "peak_driver_cpu_utilization_pct",
    "azure_worker_vm_size",
    "max_worker_nodes_provisioned",
    "total_worker_vcpus_provisioned",
    "total_worker_memory_gb_provisioned",
    "avg_worker_nodes_consumed",
    "p99_worker_nodes_consumed",
    "avg_worker_vcpus_consumed",
    "avg_worker_memory_gb_consumed",
    "avg_worker_vcpus_utilized",
    "avg_worker_memory_gb_utilized",
    "avg_worker_cpu_utilization_pct",
    "avg_worker_memory_utilization_pct",
    "peak_worker_cpu_utilization_pct",
    "peak_worker_memory_utilization_pct",
    "worker_node_provisioning_efficiency_pct",
    "worker_cpu_utilization_efficiency_pct",
    "worker_memory_utilization_efficiency_pct",
    "delta_tables_ingested",
    "processed_bytes",
    "processed_row_count",
]

# Derived field used by sizing/guardrails (not stored in Delta).
DERIVED_AGENT_FIELDS = ("p95_worker_nodes_consumed",)


class JobClusterMetrics(BaseModel):
    """One row from the centralized job_cluster_metrics Delta table."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    job_run_date: str
    workspace_id: str
    workspace_name: Optional[str] = None
    cluster_id: str
    job_id: str
    job_type: Optional[str] = None
    job_name: Optional[str] = None
    job_run_start_time_utc: Optional[str] = None
    job_run_end_time_utc: Optional[str] = None
    job_run_duration_seconds: float = 0.0
    azure_driver_vm_size: Optional[str] = None
    driver_node_count: int = 1
    driver_vcpus_consumed: Optional[float] = None
    driver_memory_gb_consumed: Optional[float] = None
    avg_driver_cpu_utilization_pct: Optional[float] = None
    avg_driver_memory_utilization_pct: Optional[float] = None
    peak_driver_cpu_utilization_pct: Optional[float] = None
    azure_worker_vm_size: str = "Standard_E8s_v3"
    max_worker_nodes_provisioned: int = 1
    total_worker_vcpus_provisioned: Optional[float] = None
    total_worker_memory_gb_provisioned: Optional[float] = None
    avg_worker_nodes_consumed: float = 0.0
    p99_worker_nodes_consumed: float = 0.0
    avg_worker_vcpus_consumed: Optional[float] = None
    avg_worker_memory_gb_consumed: Optional[float] = None
    avg_worker_vcpus_utilized: Optional[float] = None
    avg_worker_memory_gb_utilized: Optional[float] = None
    avg_worker_cpu_utilization_pct: float = 0.0
    avg_worker_memory_utilization_pct: float = 0.0
    peak_worker_cpu_utilization_pct: float = 0.0
    peak_worker_memory_utilization_pct: float = 0.0
    worker_node_provisioning_efficiency_pct: Optional[float] = None
    worker_cpu_utilization_efficiency_pct: Optional[float] = None
    worker_memory_utilization_efficiency_pct: Optional[float] = None
    delta_tables_ingested: Optional[int] = None
    processed_bytes: Optional[int] = None
    processed_row_count: Optional[int] = None

    @property
    def job_run_id(self) -> str:
        """Deprecated alias: Delta uses cluster_id as the per-run identifier."""
        return self.cluster_id

    def to_agent_dict(self) -> Dict[str, Any]:
        return enrich_metrics_dict(self.model_dump())


def metrics_record_to_dict(metric: Union[JobClusterMetrics, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(metric, JobClusterMetrics):
        return metric.to_agent_dict()
    return enrich_metrics_dict(dict(metric))


def enrich_metrics_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a metrics row for API/agent use (Delta columns + derived p95)."""
    out = dict(raw)
    if out.get("cluster_id") is None and out.get("job_run_id"):
        out["cluster_id"] = out["job_run_id"]
    if out.get("job_run_date") is None:
        out["job_run_date"] = out.get("job_date") or out.get("date")
    if (
        out.get("avg_worker_nodes_consumed") is None
        and out.get("total_worker_nodes_consumed") is not None
    ):
        out["avg_worker_nodes_consumed"] = out["total_worker_nodes_consumed"]
    if out.get("p95_worker_nodes_consumed") is None:
        out["p95_worker_nodes_consumed"] = (
            out.get("avg_worker_nodes_consumed") or out.get("p99_worker_nodes_consumed") or 0.0
        )
    return out


def run_summary_from_metric(metric: JobClusterMetrics) -> Dict[str, Any]:
    """Per-run browse row (Delta column names)."""
    d = metric.model_dump()
    return {k: d[k] for k in DELTA_TABLE_COLUMNS if k in d}


def job_list_summary_row(
    *,
    workspace_id: str,
    job_id: str,
    job_name: str,
    job_type: Optional[str],
    avg_worker_cpu_utilization_pct: float,
    avg_worker_memory_utilization_pct: float,
    total_runs: int,
    avg_job_run_duration_seconds: float,
    azure_worker_vm_size: str,
    max_worker_nodes_provisioned: int,
    last_job_run_date: str,
) -> Dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "job_id": job_id,
        "job_name": job_name,
        "job_type": job_type,
        "avg_worker_cpu_utilization_pct": avg_worker_cpu_utilization_pct,
        "avg_worker_memory_utilization_pct": avg_worker_memory_utilization_pct,
        "total_runs": total_runs,
        "avg_job_run_duration_seconds": avg_job_run_duration_seconds,
        "azure_worker_vm_size": azure_worker_vm_size,
        "max_worker_nodes_provisioned": max_worker_nodes_provisioned,
        "last_job_run_date": last_job_run_date,
    }
