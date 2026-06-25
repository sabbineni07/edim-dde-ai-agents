"""Tests for FAISS index caching."""

from unittest.mock import MagicMock, patch


def test_load_cached_faiss_reuses_same_mtime():
    from AI.src.core.retrieval import faiss_cache

    faiss_cache.invalidate_faiss_cache()
    embeddings = MagicMock()
    vs = MagicMock()

    with patch.object(faiss_cache, "faiss_index_mtime", return_value=100.0):
        with patch.object(faiss_cache, "load_faiss_vectorstore", return_value=vs) as load:
            first = faiss_cache.load_cached_faiss_vectorstore("/tmp/faiss", embeddings)
            second = faiss_cache.load_cached_faiss_vectorstore("/tmp/faiss", embeddings)
            assert first is second
            load.assert_called_once()


def test_invalidate_forces_reload():
    from AI.src.core.retrieval import faiss_cache

    faiss_cache.invalidate_faiss_cache()
    embeddings = MagicMock()
    vs1 = MagicMock()
    vs2 = MagicMock()

    with patch.object(faiss_cache, "faiss_index_mtime", return_value=100.0):
        with patch.object(faiss_cache, "load_faiss_vectorstore", side_effect=[vs1, vs2]) as load:
            first = faiss_cache.load_cached_faiss_vectorstore("/tmp/faiss2", embeddings)
            faiss_cache.invalidate_faiss_cache("/tmp/faiss2")
            second = faiss_cache.load_cached_faiss_vectorstore("/tmp/faiss2", embeddings)
            assert first is vs1
            assert second is vs2
            assert load.call_count == 2
