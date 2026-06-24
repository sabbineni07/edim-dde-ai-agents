"""Tests for RAG enable/disable helpers."""

from shared.config.rag_settings import is_rag_enabled, rag_backend


def test_rag_disabled_by_default():
    assert rag_backend({"vector_retrieval_backend": None}) == "none"
    assert not is_rag_enabled({"vector_retrieval_backend": "none"})


def test_rag_enabled_for_azure_search():
    assert is_rag_enabled({"vector_retrieval_backend": "azure_search"})


def test_rag_enabled_for_faiss():
    assert is_rag_enabled({"vector_retrieval_backend": "faiss"})
