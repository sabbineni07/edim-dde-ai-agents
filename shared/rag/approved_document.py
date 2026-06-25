"""Build retrieval text and index payloads for approved recommendations."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

_INGEST_METRIC_KEYS = (
    "job_type",
    "workflow_task_count",
    "cluster_avg_cpu_utilization_pct_of_ceiling_capacity",
    "cluster_avg_memory_utilization_pct_of_ceiling_capacity",
    "avg_vcpus_utilized_by_workload",
    "p95_worker_nodes_consumed",
    "max_worker_nodes_provisioned",
    "driver_node_count",
    "azure_worker_vm_size",
)


def _ingest_from_comparison(comparison: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not comparison:
        return {}
    current = comparison.get("current_configuration") or {}
    autoscale = current.get("autoscale") or {}
    return {
        "azure_worker_vm_size": current.get("azure_node_type"),
        "max_worker_nodes_provisioned": autoscale.get("max_workers"),
        "driver_node_count": int(autoscale.get("min_workers", 0)) + 1,
    }


def extract_job_run_ingest(rec: Any) -> Dict[str, Any]:
    """Return job_run_ingest snapshot stored on the recommendation row."""
    recommendation = rec.recommendation or {}
    if isinstance(recommendation, dict):
        ingest = recommendation.get("job_run_ingest")
        if isinstance(ingest, dict) and ingest:
            return ingest
    return _ingest_from_comparison(rec.comparison)


def build_approved_retrieval_text(rec: Any) -> str:
    """Structured text for embedding similarity (not the full JSON blob)."""
    recommendation = rec.recommendation or {}
    ingest = extract_job_run_ingest(rec)
    workload = (
        ingest.get("job_type")
        or recommendation.get("workload_type")
        or recommendation.get("job_type")
        or "Unknown"
    )

    lines = [
        f"job_id: {rec.job_id}",
        f"job_run_id: {rec.job_run_id or ''}",
        f"workspace_id: {rec.workspace_id or ''}",
        f"workload_type: {workload}",
    ]
    for key in _INGEST_METRIC_KEYS:
        if key in ("job_type",):
            continue
        val = ingest.get(key)
        if val is not None:
            lines.append(f"{key}: {val}")

    for key in ("node_type", "node_family", "min_workers", "max_workers", "vcpus"):
        val = recommendation.get(key)
        if val is not None:
            lines.append(f"recommended_{key}: {val}")

    rationale = recommendation.get("rationale") or ""
    if rationale:
        lines.append(f"rationale: {rationale}")
    if rec.explanation:
        lines.append(f"explanation: {rec.explanation}")
    if rec.pattern_analysis:
        lines.append(f"pattern_analysis: {str(rec.pattern_analysis)[:800]}")

    text = "\n".join(line for line in lines if line.strip())
    return text.strip()


def build_approved_index_payload(rec: Any) -> Dict[str, Any]:
    """Full recommendation document for Search/FAISS metadata."""
    recommendation = dict(rec.recommendation or {})
    recommendation.pop("job_run_ingest", None)
    ingest = extract_job_run_ingest(rec)
    return {
        "recommendation_id": str(rec.request_id),
        "job_id": rec.job_id,
        "job_run_id": rec.job_run_id or "",
        "workspace_id": rec.workspace_id or "",
        "workload_type": ingest.get("job_type") or recommendation.get("workload_type", "Unknown"),
        "rationale": recommendation.get("rationale", ""),
        "detailed_explanation": rec.explanation or "",
        "pattern_analysis": rec.pattern_analysis or "",
        "comparison": rec.comparison,
        "reason_codes": rec.reason_codes,
        "job_run_ingest": ingest,
        "config_quality": "approved",
        **recommendation,
    }


def build_faiss_metadata(rec: Any, payload: Dict[str, Any], retrieval_text: str) -> Dict[str, Any]:
    ingest = payload.get("job_run_ingest") or {}
    return {
        "document_type": "recommendation",
        "is_recommendation": True,
        "config_quality": "approved",
        "request_id": str(rec.request_id),
        "job_id": rec.job_id,
        "job_run_id": rec.job_run_id or "",
        "workspace_id": rec.workspace_id or "",
        "workload_type": payload.get("workload_type", "Unknown"),
        "content": retrieval_text,
        "recommendation": json.dumps(payload),
        "job_run_ingest": json.dumps(ingest) if ingest else "{}",
    }
