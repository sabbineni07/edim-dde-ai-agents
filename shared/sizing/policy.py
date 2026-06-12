"""Deterministic sizing hints from job-run ingest (90% target, 10% buffer)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from shared.models.job_run_ingest import default_sizing_policy

REASON_CODES = (
    "OVERPROVISIONED_AUTOSCALE",
    "PER_NODE_UNDERUTILIZED",
    "DRIVER_UNDERUTILIZED",
    "VM_FAMILY_MISMATCH",
    "LOW_PARALLELISM",
    "SINGLE_NODE_ELIGIBLE",
    "SINGLE_NODE_RECOMMENDED",
    "NO_CHANGE_RECOMMENDED",
    "INSUFFICIENT_EVIDENCE",
)


def recommended_min_max_workers(
    ingest: Dict[str, Any],
    *,
    buffer_pct: float = 10.0,
) -> Tuple[int, int]:
    """Floor/ceiling hint for max_workers from observed worker nodes."""
    p95 = float(ingest.get("p95_worker_nodes_consumed") or 0)
    p99 = float(ingest.get("p99_worker_nodes_consumed") or p95)
    ceiling = int(ingest.get("max_worker_nodes_provisioned") or 1)
    min_w = int(ingest.get("driver_node_count") or 1) - 1
    min_w = max(min_w, 0)

    if p95 > 0:
        base_nodes = p95
    elif p99 > 0:
        base_nodes = p99
    else:
        base_nodes = max(float(ingest.get("avg_worker_nodes_consumed") or 1), 1.0)
    buffered = math.ceil(base_nodes * (1.0 + buffer_pct / 100.0))
    max_w = max(int(buffered), 1)
    max_w = min(max_w, ceiling) if ceiling > 0 else max_w
    return max(min_w, 0), int(max_w)


def compute_sizing_hints(
    ingest: Dict[str, Any],
    sizing_policy: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Hints for LLM and guardrails: limiting resource, suggested family, worker bounds."""
    policy = sizing_policy or ingest.get("sizing_policy") or default_sizing_policy()
    target = float(policy.get("target_utilization_pct", 90.0))
    buffer = float(policy.get("capacity_buffer_pct", 10.0))

    peak_cpu = float(ingest.get("peak_worker_cpu_utilization_pct") or 0)
    peak_mem = float(ingest.get("peak_worker_memory_utilization_pct") or 0)
    avg_cpu = float(ingest.get("avg_worker_cpu_utilization_pct") or 0)
    avg_mem = float(ingest.get("avg_worker_memory_utilization_pct") or 0)
    peak_driver_cpu = float(ingest.get("peak_driver_cpu_utilization_pct") or 0)
    avg_driver_cpu = float(ingest.get("avg_driver_cpu_utilization_pct") or 0)
    avg_driver_mem = float(ingest.get("avg_driver_memory_utilization_pct") or 0)

    cluster_peak_cpu = max(peak_cpu, peak_driver_cpu)
    cluster_peak_mem = max(peak_mem, avg_driver_mem)
    cpu_headroom = cluster_peak_cpu / target if target > 0 else 0
    mem_headroom = cluster_peak_mem / target if target > 0 else 0
    limiting = "memory" if mem_headroom >= cpu_headroom else "cpu"
    if cluster_peak_cpu < 1 and cluster_peak_mem < 1:
        limiting = "unknown"
    driver_limiting = peak_driver_cpu >= peak_cpu and peak_driver_cpu >= 40

    alloc_vcpu = float(ingest.get("avg_worker_vcpus_consumed") or 0)
    util_vcpu = float(ingest.get("avg_worker_vcpus_utilized") or 0)
    alloc_mem = float(ingest.get("avg_worker_memory_gb_consumed") or 0)
    util_mem = float(ingest.get("avg_worker_memory_gb_utilized") or 0)

    vcpu_util_pct = (util_vcpu / alloc_vcpu * 100.0) if alloc_vcpu > 0 else avg_cpu
    mem_util_pct = (util_mem / alloc_mem * 100.0) if alloc_mem > 0 else avg_mem
    driver_underutilized = avg_driver_cpu < 40 and avg_driver_mem < 40
    worker_underutilized = vcpu_util_pct < 40 and mem_util_pct < 40

    suggested_family = "E"
    if limiting == "cpu" and max(vcpu_util_pct, avg_driver_cpu) > 60:
        suggested_family = "F" if cluster_peak_cpu > 70 else "D"
    elif limiting == "memory" or mem_util_pct > vcpu_util_pct:
        suggested_family = "E"

    min_w, max_w = recommended_min_max_workers(ingest, buffer_pct=buffer)
    ceiling = int(ingest.get("max_worker_nodes_provisioned") or max_w)
    p95 = float(ingest.get("p95_worker_nodes_consumed") or 0)
    over_autoscale = ceiling > max(max_w * 2, 2) and p95 > 0

    return {
        "target_utilization_pct": target,
        "capacity_buffer_pct": buffer,
        "limiting_resource": limiting,
        "suggested_vm_family": suggested_family,
        "recommended_min_workers": min_w,
        "recommended_max_workers": max_w,
        "vcpu_utilization_pct_of_allocated": round(vcpu_util_pct, 2),
        "memory_utilization_pct_of_allocated": round(mem_util_pct, 2),
        "avg_driver_cpu_utilization_pct": round(avg_driver_cpu, 2),
        "avg_driver_memory_utilization_pct": round(avg_driver_mem, 2),
        "peak_driver_cpu_utilization_pct": round(peak_driver_cpu, 2),
        "driver_limiting": driver_limiting,
        "driver_underutilized": driver_underutilized,
        "overprovisioned_autoscale": over_autoscale,
        "per_node_underutilized": driver_underutilized and worker_underutilized,
    }


def sizing_hints_for_llm(hints: Dict[str, Any]) -> Dict[str, Any]:
    """Narrow hints for the cost LLM prompt (floors/ceilings/policy; not interpretive flags)."""
    return {
        k: hints[k]
        for k in (
            "target_utilization_pct",
            "capacity_buffer_pct",
            "limiting_resource",
            "recommended_min_workers",
            "recommended_max_workers",
        )
        if k in hints
    }


def infer_reason_codes(
    ingest: Dict[str, Any],
    recommendation: Dict[str, Any],
    *,
    change_required: bool = True,
) -> List[str]:
    """Emit reason codes from job-run ingest and recommendation."""
    hints = compute_sizing_hints(ingest)
    codes: List[str] = []

    if not ingest.get("cluster_id") and not ingest.get("job_id"):
        return ["INSUFFICIENT_EVIDENCE"]

    if hints.get("overprovisioned_autoscale"):
        codes.append("OVERPROVISIONED_AUTOSCALE")
    if hints.get("driver_underutilized") and not hints.get("per_node_underutilized"):
        codes.append("DRIVER_UNDERUTILIZED")
    if hints.get("per_node_underutilized"):
        codes.append("PER_NODE_UNDERUTILIZED")

    import re

    node_type = ingest.get("azure_worker_vm_size") or ""
    fam_match = re.search(r"Standard_([DEFL])", node_type)
    current_family = fam_match.group(1).upper() if fam_match else ""
    rec_family = str(recommendation.get("node_family", "")).upper()
    if rec_family and current_family and rec_family != current_family:
        codes.append("VM_FAMILY_MISMATCH")

    if int(ingest.get("max_worker_nodes_provisioned") or 0) <= 1:
        codes.append("SINGLE_NODE_ELIGIBLE")

    if not change_required:
        codes.append("NO_CHANGE_RECOMMENDED")

    if not codes:
        codes.append("NO_CHANGE_RECOMMENDED" if not change_required else "PER_NODE_UNDERUTILIZED")

    return codes
