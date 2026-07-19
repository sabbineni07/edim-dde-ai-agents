"""Rule-based Spark failure classification for RCA seeding."""

from __future__ import annotations

import re
from typing import Any, Dict, List

RCA_CATEGORIES = (
    "sql_error",
    "data_quality",
    "resource",
    "skew_shuffle",
    "timeout_or_cancel",
    "config",
    "unknown",
)

_SQL_PATTERNS = re.compile(
    r"AnalysisException|ParseException|table(?:\s+or\s+view)?\s+not\s+found|"
    r"cannot\s+resolve|UNRESOLVED_|SparkSQL|SYNTAX_ERROR",
    re.I,
)
_DQ_PATTERNS = re.compile(
    r"null\s+constraint|schema\s+mismatch|data\s+quality|ConstraintViolation|"
    r"NOT\s+NULL|type\s+mismatch|DELTA_SCHEMA",
    re.I,
)
_RESOURCE_PATTERNS = re.compile(
    r"OutOfMemory|OOM|Java heap space|No space left|disk\s+full|"
    r"ExecutorLost|Lost executor|Container killed|MemoryError",
    re.I,
)
_SKEW_PATTERNS = re.compile(r"skew|shuffle.*(fail|error)|FetchFailed", re.I)
_TIMEOUT_PATTERNS = re.compile(r"timeout|timed\s+out|cancelled|canceled|killed by user", re.I)
_CONFIG_PATTERNS = re.compile(
    r"permission\s+denied|Unauthorized|AccessDenied|secret|credential|"
    r"SparkConnect|configuration|ConfigException",
    re.I,
)


def _text_blob(evidence_pack: Dict[str, Any]) -> str:
    parts: List[str] = []
    anchors = evidence_pack.get("raw_anchors") or {}
    pe = anchors.get("pipeline_end") or {}
    if pe.get("failure_reason"):
        parts.append(str(pe["failure_reason"]))
    attrs = pe.get("attributes") or {}
    for k in ("error_type", "error_message"):
        if attrs.get(k):
            parts.append(str(attrs[k]))
    for err in anchors.get("sql_errors") or []:
        parts.append(str(err.get("failure_reason") or ""))
        a = err.get("attributes") or {}
        parts.append(str(a.get("error_type") or ""))
        parts.append(str(a.get("error_message") or ""))
    for exc in anchors.get("top_exceptions") or []:
        parts.append(str(exc.get("exception") or ""))
        parts.append(str(exc.get("message") or ""))
    for ev in evidence_pack.get("evidence") or []:
        parts.append(str(ev.get("excerpt") or ""))
    return "\n".join(parts)


def classify_failure(evidence_pack: Dict[str, Any]) -> Dict[str, Any]:
    """Return category hint with confidence and rationale from heuristics."""
    anchors = evidence_pack.get("raw_anchors") or {}
    sql_errors: List[Dict[str, Any]] = anchors.get("sql_errors") or []
    blob = _text_blob(evidence_pack)

    if sql_errors or _SQL_PATTERNS.search(blob):
        return {
            "category": "sql_error",
            "confidence": 0.75 if sql_errors else 0.55,
            "rationale": "SQL failure events or AnalysisException-style messages present.",
        }
    if _DQ_PATTERNS.search(blob):
        return {
            "category": "data_quality",
            "confidence": 0.6,
            "rationale": "Schema/constraint/data-quality language in failure text.",
        }
    if _RESOURCE_PATTERNS.search(blob):
        return {
            "category": "resource",
            "confidence": 0.7,
            "rationale": "OOM / executor lost / disk pressure signals.",
        }
    if _SKEW_PATTERNS.search(blob) or int(anchors.get("stage_pressure_count") or 0) > 0:
        # Only upgrade to skew when skew language present; stage pressure alone stays resource-ish
        if _SKEW_PATTERNS.search(blob):
            return {
                "category": "skew_shuffle",
                "confidence": 0.55,
                "rationale": "Shuffle/skew/fetch-fail language in telemetry.",
            }
    if _TIMEOUT_PATTERNS.search(blob):
        return {
            "category": "timeout_or_cancel",
            "confidence": 0.65,
            "rationale": "Timeout or cancellation language.",
        }
    if _CONFIG_PATTERNS.search(blob):
        return {
            "category": "config",
            "confidence": 0.6,
            "rationale": "Permission/secret/config language.",
        }

    has_any = bool(
        anchors.get("pipeline_end")
        or sql_errors
        or anchors.get("top_exceptions")
        or evidence_pack.get("evidence")
    )
    return {
        "category": "unknown",
        "confidence": 0.35 if has_any else 0.1,
        "rationale": "Insufficient distinctive signals for a specific category.",
    }


def classification_hint_text(classification: Dict[str, Any]) -> str:
    return (
        f"category={classification.get('category')}, "
        f"confidence={classification.get('confidence')}, "
        f"rationale={classification.get('rationale')}"
    )
