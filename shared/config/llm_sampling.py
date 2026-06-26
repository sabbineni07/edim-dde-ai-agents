"""Resolve LLM sampling parameters from Settings (global + per-chain overrides)."""

from __future__ import annotations

from typing import Any, Literal, Tuple

ChainKind = Literal["sizing", "explanation", "default"]

_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_TOP_P = 1.0


def _get_float(settings: Any, name: str) -> float | None:
    val = getattr(settings, name, None)
    if val is None and isinstance(settings, dict):
        val = settings.get(name)
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def resolve_llm_sampling(
    settings: Any,
    chain: ChainKind = "default",
) -> Tuple[float, float]:
    """Return (temperature, top_p) for a chain; chain-specific keys override global llm_*."""
    temperature = _get_float(settings, "llm_temperature")
    top_p = _get_float(settings, "llm_top_p")

    if chain == "sizing":
        chain_temp = _get_float(settings, "sizing_llm_temperature")
        chain_top_p = _get_float(settings, "sizing_llm_top_p")
        if chain_temp is not None:
            temperature = chain_temp
        if chain_top_p is not None:
            top_p = chain_top_p
    elif chain == "explanation":
        chain_temp = _get_float(settings, "explanation_llm_temperature")
        chain_top_p = _get_float(settings, "explanation_llm_top_p")
        if chain_temp is not None:
            temperature = chain_temp
        if chain_top_p is not None:
            top_p = chain_top_p

    if temperature is None:
        temperature = _DEFAULT_TEMPERATURE
    if top_p is None:
        top_p = _DEFAULT_TOP_P

    temperature = max(0.0, min(2.0, temperature))
    top_p = max(0.0, min(1.0, top_p))
    return temperature, top_p


def resolve_rag_top_k(settings: Any) -> Tuple[int, int]:
    """Return (top_k_recommendations, top_k_jobs) for RAG retrieval."""
    rec = getattr(settings, "rag_top_k_recommendations", None)
    jobs = getattr(settings, "rag_top_k_jobs", None)
    if isinstance(settings, dict):
        rec = rec if rec is not None else settings.get("rag_top_k_recommendations")
        jobs = jobs if jobs is not None else settings.get("rag_top_k_jobs")
    try:
        rec_i = int(rec) if rec is not None else 3
    except (TypeError, ValueError):
        rec_i = 3
    try:
        jobs_i = int(jobs) if jobs is not None else 5
    except (TypeError, ValueError):
        jobs_i = 5
    return max(1, min(20, rec_i)), max(1, min(20, jobs_i))
