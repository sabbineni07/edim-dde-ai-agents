"""Validate and normalize Spark RCA LLM output into the API contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.rca.classify import RCA_CATEGORIES


def _clamp_confidence(value: Any, default: float = 0.4) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, c))


def validate_rca_llm_output(
    raw: Dict[str, Any],
    *,
    evidence_pack: Dict[str, Any],
    classification_hint: Dict[str, Any],
) -> Dict[str, Any]:
    """Clamp/normalize LLM JSON; fall back to rule classification when needed."""
    allowed_refs = {
        str(e.get("ref")) for e in (evidence_pack.get("evidence") or []) if e.get("ref")
    }
    category = str(raw.get("category") or "").strip().lower()
    if category not in RCA_CATEGORIES:
        category = str(classification_hint.get("category") or "unknown")

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        pe = (evidence_pack.get("raw_anchors") or {}).get("pipeline_end") or {}
        summary = (
            pe.get("failure_reason")
            or classification_hint.get("rationale")
            or "Unable to determine a specific root cause from available evidence."
        )

    evidence_refs = [str(r) for r in (raw.get("evidence_refs") or []) if str(r) in allowed_refs]
    if not evidence_refs and allowed_refs:
        evidence_refs = list(allowed_refs)[:3]

    evidence_out: List[Dict[str, Any]] = []
    by_ref = {str(e.get("ref")): e for e in (evidence_pack.get("evidence") or [])}
    for ref in evidence_refs:
        item = by_ref.get(ref)
        if item:
            evidence_out.append(
                {
                    "source": item.get("source"),
                    "ref": ref,
                    "excerpt": item.get("excerpt"),
                }
            )

    timeline = raw.get("timeline_highlights")
    if not isinstance(timeline, list) or not timeline:
        timeline = evidence_pack.get("timeline") or []
    timeline_out: List[Dict[str, Any]] = []
    for t in timeline[:12]:
        if not isinstance(t, dict):
            continue
        timeline_out.append(
            {
                "ts": t.get("ts"),
                "event_type": t.get("event_type"),
                "summary": str(t.get("summary") or "")[:240],
            }
        )

    contributing = raw.get("contributing_factors") or []
    if not isinstance(contributing, list):
        contributing = [str(contributing)]
    actions = raw.get("recommended_actions") or []
    if not isinstance(actions, list):
        actions = [str(actions)]

    confidence = _clamp_confidence(
        raw.get("confidence"),
        default=float(classification_hint.get("confidence") or 0.4),
    )
    signature = str(raw.get("failure_signature") or "").strip() or category

    return {
        "root_cause": {
            "category": category,
            "summary": summary,
            "confidence": confidence,
            "failure_signature": signature[:256],
        },
        "timeline": timeline_out,
        "evidence": evidence_out,
        "contributing_factors": [str(x) for x in contributing if str(x).strip()][:10],
        "recommended_actions": [str(x) for x in actions if str(x).strip()][:10],
        "raw_anchors": evidence_pack.get("raw_anchors") or {},
    }


def build_rca_response(
    *,
    request_id: UUID,
    job_id: Optional[str],
    job_run_id: str,
    task_key: Optional[str],
    validated: Dict[str, Any],
    status: str = "completed",
) -> Dict[str, Any]:
    return {
        "request_id": str(request_id),
        "job_id": job_id,
        "job_run_id": job_run_id,
        "task_key": task_key,
        "status": status,
        **validated,
    }
