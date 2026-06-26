"""Profile overrides validation and merge helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Set

from shared.config.settings import Settings

_SECRET_FIELD_HINTS = (
    "token",
    "api_key",
    "password",
    "client_secret",
    "access_token",
    "key",
)


def _flatten(prefix: str, obj: Any, out: Dict[str, Any]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}_{k}" if prefix else str(k)
            _flatten(key, v, out)
        return
    out[prefix] = obj


def flatten_overrides(overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested overrides into flat Settings field names.

    Accepts either already-flat keys (e.g. "azure_openai_deployment_name") or nested
    YAML-like groups (e.g. {"llm": {"deployment": "..."}}) that match existing YAML
    flattening conventions.
    """
    if not overrides:
        return {}

    flat: Dict[str, Any] = {}
    for k, v in overrides.items():
        if isinstance(v, dict):
            _flatten(str(k), v, flat)
        else:
            flat[str(k)] = v

    # map nested groups to Settings fields (minimal set used by profiles)
    mapped: Dict[str, Any] = {}
    for k, v in flat.items():
        if k == "llm_deployment":
            mapped["azure_openai_deployment_name"] = v
        elif k == "llm_default_model_name":
            mapped["default_model_name"] = v
        elif k == "rag_backend":
            mapped["vector_retrieval_backend"] = v
        elif k == "sizing_recommendation_auto_termination_minutes":
            mapped["recommendation_auto_termination_minutes"] = v
        elif k == "sizing_cost_retry_enabled":
            mapped["recommendation_cost_retry_enabled"] = v
        elif k == "sizing_default_confidence_score":
            mapped["default_confidence_score"] = v
        elif k == "guardrails_max_date_range_days":
            mapped["guardrail_max_date_range_days"] = v
        elif k == "llm_temperature":
            mapped["llm_temperature"] = v
        elif k == "llm_top_p":
            mapped["llm_top_p"] = v
        elif k == "sizing_temperature":
            mapped["sizing_llm_temperature"] = v
        elif k == "sizing_top_p":
            mapped["sizing_llm_top_p"] = v
        elif k == "explanation_temperature":
            mapped["explanation_llm_temperature"] = v
        elif k == "explanation_top_p":
            mapped["explanation_llm_top_p"] = v
        elif k == "rag_top_k_recommendations":
            mapped["rag_top_k_recommendations"] = v
        elif k == "rag_top_k_jobs":
            mapped["rag_top_k_jobs"] = v
        else:
            mapped[k] = v

    return mapped


def validate_profile_overrides(
    overrides: Dict[str, Any], *, allowed_fields: Iterable[str] | None = None
) -> Dict[str, Any]:
    """Validate profile overrides are safe and correspond to Settings fields.

    - Blocks likely-secret fields from being persisted via UI profiles.
    - Optionally restricts to an allowlist (recommended for UI).
    """
    flat = flatten_overrides(overrides or {})
    if not flat:
        return {}

    settings_fields: Set[str] = set(Settings.model_fields.keys())  # pydantic v2
    unknown = sorted(k for k in flat.keys() if k not in settings_fields)
    if unknown:
        raise ValueError(f"Unknown settings override fields: {unknown}")

    blocked = sorted(
        k for k in flat.keys() if any(hint in k.lower() for hint in _SECRET_FIELD_HINTS)
    )
    if blocked:
        raise ValueError(f"Secret-like fields cannot be overridden via profiles: {blocked}")

    if allowed_fields is not None:
        allowed = set(allowed_fields)
        not_allowed = sorted(k for k in flat.keys() if k not in allowed)
        if not_allowed:
            raise ValueError(f"Fields not allowed for profile overrides: {not_allowed}")

    return flat
