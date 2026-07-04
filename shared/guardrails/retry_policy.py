"""When to retry the cost LLM after guardrail adjustments."""

from __future__ import annotations

from typing import Any, Dict, List

# Material violations the LLM can fix on a second pass (not policy-only clamps).
RETRY_ON_REASONS = frozenset(
    {
        "invalid_node_family",
        "sizing_floor",
        "sizing_ceiling",
        "vcpus_out_of_range",
        "min_workers_out_of_range",
        "max_workers_out_of_range",
        "min_workers_above_max_workers",
    }
)


def should_retry_cost_recommendation(
    adjustments: List[Dict[str, Any]],
    *,
    attempt: int,
    max_attempts: int = 2,
) -> bool:
    """True if another cost-chain call may fix guardrail violations."""
    if attempt >= max_attempts:
        return False
    return any(a.get("reason") in RETRY_ON_REASONS for a in adjustments)


def build_guardrail_feedback(adjustments: List[Dict[str, Any]], *, attempt: int) -> Dict[str, Any]:
    """Structured feedback for cost-chain retry human block."""
    violations = [
        {
            "field": a.get("field"),
            "your_value": a.get("llm_value"),
            "required": a.get("applied_value"),
            "reason": a.get("reason"),
        }
        for a in adjustments
        if a.get("reason") in RETRY_ON_REASONS
    ]
    return {
        "attempt": attempt,
        "violations": violations,
        "instruction": _guardrail_retry_instruction(),
    }


def _guardrail_retry_instruction() -> str:
    try:
        from AI.src.core.prompts.loader import get_guardrail_retry_instruction

        return get_guardrail_retry_instruction()
    except Exception:
        return (
            "Revise the JSON recommendation to satisfy all constraints. "
            "Use job_run_ingest as primary; sizing_hints are advisory pre-checks."
        )
