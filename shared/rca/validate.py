"""Validate and normalize Spark RCA LLM output into the API contract."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.rca.classify import RCA_CATEGORIES

_CONFIDENCE_LABELS = {
    "high": 0.85,
    "medium": 0.6,
    "low": 0.3,
}

_CATEGORY_ALIASES = {
    "executor out-of-memory": "resource",
    "executor oom": "resource",
    "driver out-of-memory": "resource",
    "driver oom": "resource",
    "oom": "resource",
    "data skew": "skew_shuffle",
    "skew": "skew_shuffle",
    "cartesian join": "sql_error",
    "cartesian product": "sql_error",
    "delta storage lock": "config",
    "concurrent append": "config",
    "small file bottleneck": "config",
    "small files": "config",
    "schema mismatch": "data_quality",
    "delta schema": "data_quality",
}


def _clamp_confidence(value: Any, default: float = 0.4) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, c))


def _confidence_from_raw(raw: Dict[str, Any], default: float) -> float:
    if raw.get("confidence") is not None:
        try:
            return _clamp_confidence(raw.get("confidence"), default=default)
        except Exception:
            pass
    label = str(raw.get("confidence_label") or "").strip().lower()
    if label in _CONFIDENCE_LABELS:
        return _CONFIDENCE_LABELS[label]
    return _clamp_confidence(None, default=default)


def _normalize_category(raw: Dict[str, Any], classification_hint: Dict[str, Any]) -> str:
    category = str(raw.get("category") or "").strip().lower()
    if category in RCA_CATEGORIES:
        return category
    alias = _CATEGORY_ALIASES.get(category)
    if alias:
        return alias
    for needle, mapped in _CATEGORY_ALIASES.items():
        if needle in category:
            return mapped
    return str(classification_hint.get("category") or "unknown")


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text else []


def _flatten_recommendations(raw: Dict[str, Any]) -> List[str]:
    actions = _as_str_list(raw.get("recommended_actions"))
    if actions:
        return actions[:10]
    rec = raw.get("recommendations")
    if not isinstance(rec, dict):
        return []
    merged: List[str] = []
    for key in ("code_query_rewrites", "spark_delta_configs", "infrastructure"):
        for item in _as_str_list(rec.get(key)):
            if item not in merged:
                merged.append(item)
    return merged[:10]


def _factors_from_raw(raw: Dict[str, Any]) -> List[str]:
    factors = _as_str_list(raw.get("contributing_factors"))
    if factors:
        return factors[:10]
    analysis = raw.get("evidence_analysis")
    if not isinstance(analysis, dict):
        return []
    out: List[str] = []
    for key, label in (
        ("log_signals", "Log signals"),
        ("metric_anomalies", "Metric anomalies"),
        ("physical_plan_bottlenecks", "Physical plan bottlenecks"),
    ):
        text = str(analysis.get(key) or "").strip()
        if text:
            out.append(f"{label}: {text}")
    return out[:10]


def _normalize_recommendations_block(raw: Dict[str, Any]) -> Dict[str, List[str]]:
    rec = raw.get("recommendations")
    if not isinstance(rec, dict):
        rec = {}
    return {
        "code_query_rewrites": _as_str_list(rec.get("code_query_rewrites"))[:10],
        "spark_delta_configs": _as_str_list(rec.get("spark_delta_configs"))[:10],
        "infrastructure": _as_str_list(rec.get("infrastructure"))[:10],
    }


def _normalize_evidence_analysis(raw: Dict[str, Any]) -> Dict[str, str]:
    analysis = raw.get("evidence_analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    return {
        "log_signals": str(analysis.get("log_signals") or "").strip(),
        "metric_anomalies": str(analysis.get("metric_anomalies") or "").strip(),
        "physical_plan_bottlenecks": str(analysis.get("physical_plan_bottlenecks") or "").strip(),
    }


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
    category = _normalize_category(raw, classification_hint)

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

    contributing = _factors_from_raw(raw)
    actions = _flatten_recommendations(raw)
    recommendations = _normalize_recommendations_block(raw)
    evidence_analysis = _normalize_evidence_analysis(raw)

    confidence = _confidence_from_raw(
        raw,
        default=float(classification_hint.get("confidence") or 0.4),
    )
    label = str(raw.get("confidence_label") or "").strip()
    if not label:
        if confidence >= 0.75:
            label = "High"
        elif confidence >= 0.45:
            label = "Medium"
        else:
            label = "Low"

    job_status = str(raw.get("job_status") or "FAILED").strip().upper().replace(" ", "_")
    if job_status not in {"FAILED", "DEGRADED", "SUCCESS_WITH_WARNINGS"}:
        job_status = "FAILED"

    signature = str(raw.get("failure_signature") or "").strip() or category

    return {
        "job_status": job_status,
        "root_cause": {
            "category": category,
            "summary": summary,
            "confidence": confidence,
            "confidence_label": label,
            "failure_signature": signature[:256],
        },
        "evidence_analysis": evidence_analysis,
        "recommendations": recommendations,
        "timeline": timeline_out,
        "evidence": evidence_out,
        "contributing_factors": contributing,
        "recommended_actions": actions,
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
