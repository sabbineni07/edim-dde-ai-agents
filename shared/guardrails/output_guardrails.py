"""Output guardrails: validate and clamp LLM recommendation output."""

from typing import Any, Dict, List, Optional, Tuple

from shared.config.settings import settings
from shared.guardrails.sku_allowlist import nearest_allowed_node_type
from shared.sizing.policy import recommended_min_max_workers
from shared.utils.logging import get_logger

logger = get_logger(__name__)

VALID_NODE_FAMILIES = ("D", "E", "F", "L")
VCPUS_MIN, VCPUS_MAX = 4, 64
MIN_WORKERS_MIN, MIN_WORKERS_MAX = 0, 32
MAX_WORKERS_MIN, MAX_WORKERS_MAX = 1, 64
RATIONALE_MAX_LENGTH = 2000


def _record_adjustment(
    adjustments: List[Dict[str, Any]],
    *,
    field: str,
    llm_value: Any,
    applied_value: Any,
    reason: str,
) -> None:
    if llm_value == applied_value:
        return
    adjustments.append(
        {
            "field": field,
            "llm_value": llm_value,
            "applied_value": applied_value,
            "reason": reason,
        }
    )


def sync_rationale_with_applied_config(out: Dict[str, Any]) -> None:
    """Ensure rationale cites the same min/max workers and auto-termination as the JSON fields."""
    rationale = str(out.get("rationale") or "").strip()
    max_w = out.get("max_workers")
    min_w = out.get("min_workers")
    atm = out.get("auto_termination_minutes")
    applied = (
        f"Applied autoscale (authoritative): min_workers={min_w}, max_workers={max_w}, "
        f"auto_termination_minutes={atm} (terminate immediately when the job completes)."
    )
    if applied not in rationale:
        if rationale:
            rationale = f"{rationale.rstrip()} {applied}"
        else:
            rationale = applied
        out["rationale"] = rationale


def validate_and_clamp_recommendation(
    rec: Dict[str, Any],
    job_run_ingest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate recommendation dict from cost chain and clamp values to safe bounds."""
    out, _ = validate_and_clamp_with_adjustments(rec, job_run_ingest=job_run_ingest)
    return out


def validate_and_clamp_with_adjustments(
    rec: Dict[str, Any],
    job_run_ingest: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Clamp recommendation and return (applied_config, guardrail_adjustments)."""
    if not rec or not isinstance(rec, dict):
        out = _default_recommendation("Missing or invalid recommendation object")
        return out, [
            {
                "field": "_recommendation",
                "llm_value": rec,
                "applied_value": "default",
                "reason": "invalid_recommendation_object",
            }
        ]

    adjustments: List[Dict[str, Any]] = []
    out: Dict[str, Any] = dict(rec)

    family = rec.get("node_family")
    if family is None or str(family).strip().upper() not in VALID_NODE_FAMILIES:
        applied_family = "E"
        out["node_family"] = applied_family
        _record_adjustment(
            adjustments,
            field="node_family",
            llm_value=family,
            applied_value=applied_family,
            reason="invalid_node_family",
        )
        logger.warning(
            "output_guardrail",
            field="node_family",
            value=family,
            clamped_to=applied_family,
        )
    else:
        out["node_family"] = str(family).strip().upper()

    try:
        v = int(rec.get("vcpus", 8))
        clamped = max(VCPUS_MIN, min(VCPUS_MAX, v))
        out["vcpus"] = clamped
        if clamped != v:
            _record_adjustment(
                adjustments,
                field="vcpus",
                llm_value=v,
                applied_value=clamped,
                reason="vcpus_out_of_range",
            )
            logger.warning("output_guardrail", field="vcpus", value=v, clamped_to=clamped)
    except (TypeError, ValueError):
        out["vcpus"] = 8
        _record_adjustment(
            adjustments,
            field="vcpus",
            llm_value=rec.get("vcpus"),
            applied_value=8,
            reason="vcpus_out_of_range",
        )

    try:
        v = int(rec.get("min_workers", 0))
        clamped = max(MIN_WORKERS_MIN, min(MIN_WORKERS_MAX, v))
        out["min_workers"] = clamped
        if clamped != v:
            _record_adjustment(
                adjustments,
                field="min_workers",
                llm_value=v,
                applied_value=clamped,
                reason="min_workers_out_of_range",
            )
    except (TypeError, ValueError):
        out["min_workers"] = 0
        _record_adjustment(
            adjustments,
            field="min_workers",
            llm_value=rec.get("min_workers"),
            applied_value=0,
            reason="min_workers_out_of_range",
        )

    llm_max_raw = rec.get("max_workers")
    try:
        v = int(rec.get("max_workers", 8))
        clamped = max(MAX_WORKERS_MIN, min(MAX_WORKERS_MAX, v))
        out["max_workers"] = clamped
        if clamped != v:
            _record_adjustment(
                adjustments,
                field="max_workers",
                llm_value=v,
                applied_value=clamped,
                reason="max_workers_out_of_range",
            )
    except (TypeError, ValueError):
        out["max_workers"] = 8
        _record_adjustment(
            adjustments,
            field="max_workers",
            llm_value=llm_max_raw,
            applied_value=8,
            reason="max_workers_out_of_range",
        )

    if out["min_workers"] > out["max_workers"]:
        prev_min = out["min_workers"]
        out["min_workers"] = out["max_workers"]
        _record_adjustment(
            adjustments,
            field="min_workers",
            llm_value=prev_min,
            applied_value=out["min_workers"],
            reason="min_workers_above_max_workers",
        )
        logger.warning("output_guardrail", field="min_workers", reason="clamped to max_workers")

    llm_max_before_floor = out["max_workers"]
    if job_run_ingest:
        _, floor_max = recommended_min_max_workers(job_run_ingest)
        ceiling_max = int(
            job_run_ingest.get("max_worker_nodes_provisioned")
            or job_run_ingest.get("max_worker_nodes_cluster_ceiling")
            or floor_max
        )
        if out["max_workers"] < floor_max:
            applied = min(floor_max, MAX_WORKERS_MAX)
            _record_adjustment(
                adjustments,
                field="max_workers",
                llm_value=llm_max_before_floor,
                applied_value=applied,
                reason="sizing_floor",
            )
            out["max_workers"] = applied
            logger.warning(
                "output_guardrail",
                field="max_workers",
                reason="raised to sizing floor",
                floor=floor_max,
                llm_value=llm_max_before_floor,
            )
        elif out["max_workers"] > ceiling_max and ceiling_max > 0:
            applied = min(ceiling_max, MAX_WORKERS_MAX)
            _record_adjustment(
                adjustments,
                field="max_workers",
                llm_value=llm_max_before_floor,
                applied_value=applied,
                reason="sizing_ceiling",
            )
            out["max_workers"] = applied
            logger.warning(
                "output_guardrail",
                field="max_workers",
                reason="lowered to cluster ceiling",
                ceiling=ceiling_max,
                llm_value=llm_max_before_floor,
            )
        sku_before = out.get("azure_node_type")
        current_type = job_run_ingest.get("azure_worker_vm_size")
        mapped = nearest_allowed_node_type(
            out["node_family"],
            out["vcpus"],
            current_node_type=current_type,
        )
        out["azure_node_type"] = mapped
        if sku_before != mapped:
            _record_adjustment(
                adjustments,
                field="azure_node_type",
                llm_value=sku_before,
                applied_value=mapped,
                reason="sku_mapped",
            )

    immediate = int(settings.recommendation_auto_termination_minutes)
    llm_atm = rec.get("auto_termination_minutes")
    if llm_atm != immediate:
        _record_adjustment(
            adjustments,
            field="auto_termination_minutes",
            llm_value=llm_atm,
            applied_value=immediate,
            reason="auto_termination_policy",
        )
        logger.info(
            "output_guardrail",
            field="auto_termination_minutes",
            llm_value=llm_atm,
            clamped_to=immediate,
        )
    out["auto_termination_minutes"] = immediate

    rationale = rec.get("rationale", "")
    if rationale is not None and isinstance(rationale, str):
        if len(rationale) > RATIONALE_MAX_LENGTH:
            truncated = rationale[: RATIONALE_MAX_LENGTH - 3] + "..."
            _record_adjustment(
                adjustments,
                field="rationale",
                llm_value=f"{len(rationale)} chars",
                applied_value=f"{len(truncated)} chars",
                reason="rationale_truncated",
            )
            out["rationale"] = truncated
        else:
            out["rationale"] = rationale
    else:
        out["rationale"] = str(rationale) if rationale is not None else "No rationale provided."

    sync_rationale_with_applied_config(out)

    return out, adjustments


def _default_recommendation(reason: str) -> Dict[str, Any]:
    """Return a safe default recommendation when validation fails."""
    return {
        "node_family": "E",
        "vcpus": 8,
        "min_workers": 1,
        "max_workers": 8,
        "auto_termination_minutes": settings.recommendation_auto_termination_minutes,
        "rationale": f"Conservative fallback: {reason}",
    }
