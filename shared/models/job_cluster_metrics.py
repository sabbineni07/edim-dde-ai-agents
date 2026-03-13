"""Job cluster metrics data model."""

from typing import List, Optional

from pydantic import BaseModel


class JobClusterMetrics(BaseModel):
    date: str
    workspace_id: str
    job_id: str
    job_run_id: str
    job_duration_seconds: float
    task_count: int
    parallelism_ratio: float
    avg_cpu_utilization_pct: float
    avg_memory_utilization_pct: float
    peak_cpu_utilization_pct: float
    peak_memory_utilization_pct: float
    avg_nodes_consumed: float
    p95_nodes_consumed: float
    p99_nodes_consumed: float
    total_cost_usd: float
    cost_per_hour_usd: float
    rows_added: Optional[int] = None
    num_of_tables: Optional[int] = None
    workload_type: Optional[str] = None
    current_node_type: str
    current_min_workers: int
    current_max_workers: int
    job_date: Optional[str] = None
    workspace_name: Optional[str] = None
    job_name: Optional[str] = None
    cluster_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    delta_tables: Optional[List[str]] = None
    provisioning_efficiency_pct: Optional[float] = None
    cpu_utilization_efficiency_pct: Optional[float] = None
    memory_utilization_efficiency_pct: Optional[float] = None
    max_nodes_provisioned: Optional[int] = None
    total_cpus_provisioned: Optional[int] = None
    total_memory_gb_provisioned: Optional[float] = None

    class Config:
        from_attributes = True
