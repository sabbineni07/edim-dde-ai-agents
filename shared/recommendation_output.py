"""Map agent output to comparison-style payload (schema_version 2.0.0 subset)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _parse_vm_generation(node_type: str) -> str:
    if "_v" in node_type:
        return "v" + node_type.rsplit("_v", 1)[-1].split("_")[0]
    return "v3"


def _cluster_config_from_ingest_and_rec(
    ingest: Dict[str, Any],
    rec: Dict[str, Any],
    *,
    recommended: bool,
) -> Dict[str, Any]:
    node_type = (
        rec.get("node_type")
        if recommended
        else ingest.get("azure_worker_vm_size", "Standard_E8s_v3")
    )
    family = (
        str(rec.get("node_family", "")).upper()
        if recommended
        else (node_type[9:10].upper() if len(node_type) > 9 else "E")
    )
    vcpus = int(rec.get("vcpus", 8) if recommended else _vcpus_from_type(node_type))
    return {
        "azure_node_type": node_type,
        "vm_family": family,
        "vm_generation": _parse_vm_generation(node_type),
        "vcpus_per_node": max(4, vcpus),
        "memory_gb_per_node": 0,
        "cluster_topology": "multi_node",
        "autoscale": {
            "min_workers": int(
                rec.get("min_workers", 0)
                if recommended
                else max(int(ingest.get("driver_node_count", 1)) - 1, 0)
            ),
            "max_workers": int(
                rec.get("max_workers", 8)
                if recommended
                else ingest.get("max_worker_nodes_provisioned", 1)
            ),
        },
        "notes": rec.get("rationale", "") if recommended else "",
    }


def _vcpus_from_type(node_type: str) -> int:
    import re

    m = re.search(r"Standard_[DEFL](\d+)", node_type or "")
    return int(m.group(1)) if m else 8


def build_comparison(
    ingest: Dict[str, Any],
    recommendation: Dict[str, Any],
    *,
    change_required: bool = True,
    rationale: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build comparison block for API consumers."""
    bullets = rationale or []
    if not bullets and recommendation.get("rationale"):
        bullets = [str(recommendation["rationale"])]
    return {
        "change_required": change_required,
        "rationale": bullets,
        "current_configuration": _cluster_config_from_ingest_and_rec(
            ingest, recommendation, recommended=False
        ),
        "recommended_configuration": _cluster_config_from_ingest_and_rec(
            ingest, recommendation, recommended=True
        ),
        "expected_directional_impact": {
            "cost": "lower" if change_required else "same",
            "performance": "same",
            "risk": (
                str(recommendation.get("risk_level", "low")).lower()
                if str(recommendation.get("risk_level", "low")).lower() in ("low", "medium", "high")
                else "low"
            ),
        },
        "single_node": {
            "eligible": int(ingest.get("max_worker_nodes_provisioned") or 0) <= 1,
            "recommended": False,
            "notes": [],
        },
    }


def build_recommendation_response_v2(
    *,
    recommendation_id: str,
    ingest: Dict[str, Any],
    recommendation: Dict[str, Any],
    reason_codes: List[str],
    pattern_analysis: str = "",
    change_required: bool = True,
) -> Dict[str, Any]:
    """Top-level schema_version 2.0.0 style object (lifecycle defaults)."""
    comparison = build_comparison(
        ingest,
        recommendation,
        change_required=change_required,
        rationale=recommendation.get("rationale_bullets"),
    )
    return {
        "schema_version": "2.0.0",
        "recommendation_id": recommendation_id,
        "analysis_summary": {
            "cluster_level_state": pattern_analysis[:2000] if pattern_analysis else "",
            "per_node_efficiency": recommendation.get("rationale", ""),
            "key_evidence": [
                k
                for k in (
                    "cluster_avg_cpu_utilization_pct_of_ceiling_capacity",
                    "cluster_avg_memory_utilization_pct_of_ceiling_capacity",
                    "avg_vcpus_utilized_by_workload",
                    "p95_worker_nodes_consumed",
                    "workflow_task_count",
                )
                if ingest.get(k) is not None
            ],
        },
        "reason_codes": reason_codes,
        "comparison": comparison,
        "pipeline_recommendations": [],
        "lifecycle": {
            "status": "RECOMMENDED",
            "accepted": False,
            "accepted_by": None,
            "accepted_at": None,
            "applied": False,
            "applied_by": None,
            "applied_at": None,
            "verified": False,
            "verified_by": None,
            "verified_at": None,
            "verification_notes": [],
        },
        "maturity": {"maturity_score": 0, "maturity_level": "generated"},
        "confidence_notes": [],
    }
