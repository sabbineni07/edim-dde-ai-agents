"""Helpers for optional RAG (Azure AI Search / FAISS) on recommendation runs."""

from __future__ import annotations

from typing import Any

RAG_DISABLED_BACKENDS = frozenset({"none", "off", "disabled"})


def rag_backend(settings: Any) -> str:
    """Normalized vector_retrieval_backend value."""
    raw = getattr(settings, "vector_retrieval_backend", None)
    if raw is None and isinstance(settings, dict):
        raw = settings.get("vector_retrieval_backend")
    return (raw or "none").strip().lower()


def is_rag_enabled(settings: Any) -> bool:
    """True when RAG should run for this settings bundle."""
    return rag_backend(settings) not in RAG_DISABLED_BACKENDS
