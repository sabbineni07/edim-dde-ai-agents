"""LLM-oriented flat ingest for a single Databricks job run."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field

from shared.models.job_cluster_metrics import JobClusterMetrics

# Re-export-friendly alias for prompts and logs
SizingPolicyDict = Dict[str, float]


def default_sizing_policy() -> SizingPolicyDict:
    return {"target_utilization_pct": 90.0, "capacity_buffer_pct": 10.0}


class JobRunIngest(BaseModel):
    """Self-descriptive metrics for one job run (Copilot databricks-efficiency ingest shape)."""

    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    cluster_id: Optional[str] = None
    job_id: str
    job_name: Optional[str] = None
    job_run_id: str
    job_run_date: Optional[str] = None
    run_start_time_utc: Optional[str] = None
    run_end_time_utc: Optional[str] = None
    duration_seconds: Optional[float] = None

    azure_worker_vm_size: str = "Standard_E8s_v3"
    max_worker_nodes_cluster_ceiling: int = 1
    total_vcpus_cluster_ceiling: Optional[float] = None
    total_memory_gb_cluster_ceiling: Optional[float] = None

    avg_worker_nodes_consumed: float = 0.0
    p95_worker_nodes_consumed: float = 0.0
    p99_worker_nodes_consumed: float = 0.0

    avg_vcpus_allocated_active_cluster: Optional[float] = None
    avg_memory_gb_allocated_active_cluster: Optional[float] = None
    avg_vcpus_utilized_by_workload: Optional[float] = None
    avg_memory_gb_utilized_by_workload: Optional[float] = None

    cluster_avg_cpu_utilization_pct_of_ceiling_capacity: float = 0.0
    cluster_avg_memory_utilization_pct_of_ceiling_capacity: float = 0.0
    peak_cpu_utilization_pct: float = 0.0
    peak_memory_utilization_pct: float = 0.0

    workflow_task_count: int = 0
    parallelism_ratio: float = 1.0

    avg_cpu_user_pct: Optional[float] = None
    avg_cpu_system_pct: Optional[float] = None
    avg_cpu_wait_pct: Optional[float] = None

    provisioning_efficiency_pct: Optional[float] = None
    cpu_utilization_efficiency_pct: Optional[float] = None
    memory_utilization_efficiency_pct: Optional[float] = None

    workload_type: Optional[str] = None
    current_min_workers: int = 1

    class Config:
        extra = "ignore"


def _parse_vcpus_from_node_type(node_type: str) -> int:
    import re

    if not node_type:
        return 8
    match = re.search(r"Standard_[DEFL](\d+)", node_type)
    if match:
        return int(match.group(1))
    return 8


def _memory_gb_per_node_from_type(node_type: str, vcpus: int) -> float:
    """Rough Azure ratio: E ~8 GB/vCPU, D ~4 GB/vCPU, default 8."""
    if not node_type:
        return float(vcpus * 8)
    upper = node_type.upper()
    if "_E" in upper or upper.startswith("STANDARD_E"):
        return float(vcpus * 8)
    if "_D" in upper or upper.startswith("STANDARD_D"):
        return float(vcpus * 4)
    return float(vcpus * 8)


def _derive_allocated_utilized(
    vcpus_per_node: int,
    memory_gb_per_node: float,
    avg_nodes: float,
    avg_cpu_pct: float,
    avg_memory_pct: float,
    total_vcpus_ceiling: Optional[float],
    total_memory_gb_ceiling: Optional[float],
) -> Dict[str, float]:
    """Estimate allocated vs utilized when not supplied by DE."""
    allocated_vcpus = (
        float(total_vcpus_ceiling)
        if total_vcpus_ceiling and total_vcpus_ceiling > 0
        else vcpus_per_node * max(avg_nodes, 1.0)
    )
    allocated_memory_gb = (
        float(total_memory_gb_ceiling)
        if total_memory_gb_ceiling and total_memory_gb_ceiling > 0
        else memory_gb_per_node * max(avg_nodes, 1.0)
    )
    cpu_ratio = min(1.0, max(0.0, avg_cpu_pct / 100.0))
    mem_ratio = min(1.0, max(0.0, avg_memory_pct / 100.0))
    return {
        "avg_vcpus_allocated_active_cluster": round(allocated_vcpus, 2),
        "avg_memory_gb_allocated_active_cluster": round(allocated_memory_gb, 2),
        "avg_vcpus_utilized_by_workload": round(allocated_vcpus * cpu_ratio, 2),
        "avg_memory_gb_utilized_by_workload": round(allocated_memory_gb * mem_ratio, 2),
    }


def to_llm_ingest_dict(
    metrics: Union[JobClusterMetrics, Dict[str, Any]],
    *,
    sizing_policy: Optional[SizingPolicyDict] = None,
) -> Dict[str, Any]:
    """Map internal metrics to flat Copilot-style ingest for LLM prompts."""
    if isinstance(metrics, JobClusterMetrics):
        raw = metrics.model_dump() if hasattr(metrics, "model_dump") else metrics.dict()
    else:
        raw = dict(metrics)

    node_type = raw.get("azure_worker_vm_size") or raw.get("current_node_type") or "Standard_E8s_v3"
    vcpus_node = _parse_vcpus_from_node_type(node_type)
    mem_gb_node = _memory_gb_per_node_from_type(node_type, vcpus_node)
    avg_nodes = float(raw.get("avg_worker_nodes_consumed") or raw.get("avg_nodes_consumed") or 0)
    avg_cpu = float(
        raw.get("cluster_avg_cpu_utilization_pct_of_ceiling_capacity")
        or raw.get("avg_cpu_utilization_pct")
        or raw.get("avg_cpu_utilization")
        or 0
    )
    avg_mem = float(
        raw.get("cluster_avg_memory_utilization_pct_of_ceiling_capacity")
        or raw.get("avg_memory_utilization_pct")
        or raw.get("avg_memory_utilization")
        or 0
    )

    derived = _derive_allocated_utilized(
        vcpus_node,
        mem_gb_node,
        avg_nodes,
        avg_cpu,
        avg_mem,
        raw.get("total_vcpus_cluster_ceiling") or raw.get("total_cpus_provisioned"),
        raw.get("total_memory_gb_cluster_ceiling") or raw.get("total_memory_gb_provisioned"),
    )

    ingest = JobRunIngest(
        workspace_id=raw.get("workspace_id"),
        workspace_name=raw.get("workspace_name"),
        cluster_id=raw.get("cluster_id"),
        job_id=str(raw.get("job_id", "")),
        job_name=raw.get("job_name"),
        job_run_id=str(raw.get("job_run_id") or raw.get("cluster_id") or raw.get("job_id", "")),
        job_run_date=raw.get("job_run_date") or raw.get("job_date") or raw.get("date"),
        run_start_time_utc=raw.get("run_start_time_utc") or raw.get("start_time"),
        run_end_time_utc=raw.get("run_end_time_utc") or raw.get("end_time"),
        duration_seconds=raw.get("duration_seconds") or raw.get("job_duration_seconds"),
        azure_worker_vm_size=node_type,
        max_worker_nodes_cluster_ceiling=int(
            raw.get("max_worker_nodes_cluster_ceiling") or raw.get("current_max_workers") or 1
        ),
        total_vcpus_cluster_ceiling=_float_or_none(
            raw.get("total_vcpus_cluster_ceiling") or raw.get("total_cpus_provisioned")
        ),
        total_memory_gb_cluster_ceiling=_float_or_none(
            raw.get("total_memory_gb_cluster_ceiling") or raw.get("total_memory_gb_provisioned")
        ),
        avg_worker_nodes_consumed=avg_nodes,
        p95_worker_nodes_consumed=float(
            raw.get("p95_worker_nodes_consumed") or raw.get("p95_nodes_consumed") or 0
        ),
        p99_worker_nodes_consumed=float(
            raw.get("p99_worker_nodes_consumed") or raw.get("p99_nodes_consumed") or 0
        ),
        avg_vcpus_allocated_active_cluster=_float_or_none(
            raw.get("avg_vcpus_allocated_active_cluster")
            or derived["avg_vcpus_allocated_active_cluster"]
        ),
        avg_memory_gb_allocated_active_cluster=_float_or_none(
            raw.get("avg_memory_gb_allocated_active_cluster")
            or derived["avg_memory_gb_allocated_active_cluster"]
        ),
        avg_vcpus_utilized_by_workload=_float_or_none(
            raw.get("avg_vcpus_utilized_by_workload") or derived["avg_vcpus_utilized_by_workload"]
        ),
        avg_memory_gb_utilized_by_workload=_float_or_none(
            raw.get("avg_memory_gb_utilized_by_workload")
            or derived["avg_memory_gb_utilized_by_workload"]
        ),
        cluster_avg_cpu_utilization_pct_of_ceiling_capacity=avg_cpu,
        cluster_avg_memory_utilization_pct_of_ceiling_capacity=avg_mem,
        peak_cpu_utilization_pct=float(
            raw.get("peak_cpu_utilization_pct") or raw.get("peak_cpu_utilization") or 0
        ),
        peak_memory_utilization_pct=float(
            raw.get("peak_memory_utilization_pct") or raw.get("peak_memory_utilization") or 0
        ),
        workflow_task_count=int(raw.get("workflow_task_count") or raw.get("task_count") or 0),
        parallelism_ratio=float(raw.get("parallelism_ratio") or 1.0),
        avg_cpu_user_pct=_float_or_none(raw.get("avg_cpu_user_pct")),
        avg_cpu_system_pct=_float_or_none(raw.get("avg_cpu_system_pct")),
        avg_cpu_wait_pct=_float_or_none(raw.get("avg_cpu_wait_pct")),
        provisioning_efficiency_pct=_float_or_none(raw.get("provisioning_efficiency_pct")),
        cpu_utilization_efficiency_pct=_float_or_none(raw.get("cpu_utilization_efficiency_pct")),
        memory_utilization_efficiency_pct=_float_or_none(
            raw.get("memory_utilization_efficiency_pct")
        ),
        workload_type=raw.get("workload_type"),
        current_min_workers=int(raw.get("current_min_workers") or 1),
    )

    out = ingest.model_dump(exclude_none=True)
    if sizing_policy:
        out["sizing_policy"] = sizing_policy
    return out


def format_job_run_ingest_for_llm(ingest: Dict[str, Any]) -> str:
    """Pretty JSON for chain prompts."""
    return json.dumps(ingest, indent=2, default=str)


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
