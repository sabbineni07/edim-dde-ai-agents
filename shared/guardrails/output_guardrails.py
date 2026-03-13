"""Output guardrails: validate and clamp LLM recommendation output."""

from typing import Any, Dict

from shared.utils.logging import get_logger

logger = get_logger(__name__)

VALID_NODE_FAMILIES = ("D", "E", "F", "L")
VCPUS_MIN, VCPUS_MAX = 1, 64
MIN_WORKERS_MIN, MIN_WORKERS_MAX = 0, 32
MAX_WORKERS_MIN, MAX_WORKERS_MAX = 1, 64
RATIONALE_MAX_LENGTH = 2000


def validate_and_clamp_recommendation(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Validate recommendation dict from cost chain and clamp values to safe bounds.

    - node_family: must be one of D, E, F, L; default E if invalid
    - vcpus: clamp to [1, 64]
    - min_workers: clamp to [0, 32]
    - max_workers: clamp to [1, 64], and ensure min_workers <= max_workers
    - auto_termination_minutes: allow None or non-negative int
    - rationale: truncate if over max length (keep string)

    Returns a new dict with validated/clamped values; does not mutate input.
    """
    if not rec or not isinstance(rec, dict):
        return _default_recommendation("Missing or invalid recommendation object")

    out: Dict[str, Any] = dict(rec)

    # node_family
    family = rec.get("node_family")
    if family is None or str(family).strip().upper() not in VALID_NODE_FAMILIES:
        out["node_family"] = "E"
        logger.warning(
            "output_guardrail",
            field="node_family",
            value=family,
            clamped_to="E",
        )
    else:
        out["node_family"] = str(family).strip().upper()

    # vcpus
    try:
        v = int(rec.get("vcpus", 8))
        out["vcpus"] = max(VCPUS_MIN, min(VCPUS_MAX, v))
        if out["vcpus"] != v:
            logger.warning("output_guardrail", field="vcpus", value=v, clamped_to=out["vcpus"])
    except (TypeError, ValueError):
        out["vcpus"] = 8
        logger.warning("output_guardrail", field="vcpus", value=rec.get("vcpus"), clamped_to=8)

    # min_workers
    try:
        v = int(rec.get("min_workers", 0))
        out["min_workers"] = max(MIN_WORKERS_MIN, min(MIN_WORKERS_MAX, v))
        if out["min_workers"] != v:
            logger.warning(
                "output_guardrail", field="min_workers", value=v, clamped_to=out["min_workers"]
            )
    except (TypeError, ValueError):
        out["min_workers"] = 0
        logger.warning(
            "output_guardrail", field="min_workers", value=rec.get("min_workers"), clamped_to=0
        )

    # max_workers
    try:
        v = int(rec.get("max_workers", 8))
        out["max_workers"] = max(MAX_WORKERS_MIN, min(MAX_WORKERS_MAX, v))
        if out["max_workers"] != v:
            logger.warning(
                "output_guardrail", field="max_workers", value=v, clamped_to=out["max_workers"]
            )
    except (TypeError, ValueError):
        out["max_workers"] = 8
        logger.warning(
            "output_guardrail", field="max_workers", value=rec.get("max_workers"), clamped_to=8
        )

    # Ensure min_workers <= max_workers
    if out["min_workers"] > out["max_workers"]:
        out["min_workers"] = out["max_workers"]
        logger.warning("output_guardrail", field="min_workers", reason="clamped to max_workers")

    # auto_termination_minutes
    atm = rec.get("auto_termination_minutes")
    if atm is not None:
        try:
            v = int(atm)
            out["auto_termination_minutes"] = v if v >= 0 else None
        except (TypeError, ValueError):
            out["auto_termination_minutes"] = None
    # else leave as-is (None or missing)

    # rationale: keep string, truncate if too long
    rationale = rec.get("rationale", "")
    if rationale is not None and isinstance(rationale, str):
        if len(rationale) > RATIONALE_MAX_LENGTH:
            out["rationale"] = rationale[: RATIONALE_MAX_LENGTH - 3] + "..."
            logger.warning("output_guardrail", field="rationale", reason="truncated")
        else:
            out["rationale"] = rationale
    else:
        out["rationale"] = str(rationale) if rationale is not None else "No rationale provided."

    return out


def _default_recommendation(reason: str) -> Dict[str, Any]:
    """Return a safe default recommendation when validation fails."""
    return {
        "node_family": "E",
        "vcpus": 8,
        "min_workers": 1,
        "max_workers": 8,
        "auto_termination_minutes": None,
        "rationale": f"Conservative fallback: {reason}",
    }
