"""LLM-oriented job-run ingest for cluster sizing recommendations."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field

from shared.models.job_cluster_metrics import (
    JobClusterMetrics,
    enrich_metrics_dict,
    metrics_record_to_dict,
)

SizingPolicyDict = Dict[str, float]


def default_sizing_policy() -> SizingPolicyDict:
    return {"target_utilization_pct": 90.0, "capacity_buffer_pct": 10.0}


class JobRunIngest(BaseModel):
    """Observed metrics and configuration for one job run, passed to LLM chains."""

    model_config = {"extra": "allow"}

    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    cluster_id: str
    job_id: str
    job_name: Optional[str] = None
    job_type: Optional[str] = None
    job_run_date: Optional[str] = None
    job_run_start_time_utc: Optional[str] = None
    job_run_end_time_utc: Optional[str] = None
    job_run_duration_seconds: Optional[float] = None
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
    p95_worker_nodes_consumed: float = 0.0
    p99_worker_nodes_consumed: float = 0.0
    avg_worker_vcpus_consumed: Optional[float] = None
    avg_worker_memory_gb_consumed: Optional[float] = None
    avg_worker_vcpus_utilized: Optional[float] = None
    avg_worker_memory_gb_utilized: Optional[float] = None
    avg_worker_cpu_utilization_pct: float = 0.0
    avg_worker_memory_utilization_pct: float = 0.0
    peak_worker_cpu_utilization_pct: float = 0.0
    peak_worker_memory_utilization_pct: float = 0.0
    worker_node_provisioning_efficency_pct: Optional[float] = None
    worker_cpu_utilization_efficiency_pct: Optional[float] = None
    worker_memory_utilization_efficency_pct: Optional[float] = Field(
        default=None,
        validation_alias="worker_memory_utilization-efficency_pct",
    )
    delta_tables_ingested: Optional[int] = None
    processed_bytes: Optional[int] = None
    processed_row_count: Optional[int] = None


def to_llm_ingest_dict(
    metrics: Union[JobClusterMetrics, Dict[str, Any]],
    *,
    sizing_policy: Optional[SizingPolicyDict] = None,
) -> Dict[str, Any]:
    """Map metrics to flat job-run ingest JSON for LLM prompts."""
    out = metrics_record_to_dict(metrics)
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
