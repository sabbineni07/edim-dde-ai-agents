"""Tests for approve-only RAG indexing orchestration."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4


def test_index_skips_when_rag_disabled():
    from shared.rag.approved_indexing import index_approved_recommendation

    rec = SimpleNamespace(
        request_id=uuid4(),
        lifecycle_status="APPROVED",
        request_log_request_id=None,
        workspace_id="ws-1",
        recommendation={"rationale": "x"},
        explanation="y",
        pattern_analysis="",
        comparison=None,
        job_id="j",
        job_run_id="r",
        reason_codes=[],
    )

    with patch("shared.rag.approved_indexing.DATABASE_AVAILABLE", True):
        with patch("shared.rag.approved_indexing.get_database_session") as mock_session:
            mock_session.return_value.query.return_value.filter.return_value.first.return_value = (
                rec
            )
            with patch(
                "shared.rag.approved_indexing.resolve_rag_settings_for_history",
                return_value=None,
            ):
                assert index_approved_recommendation(rec.request_id) is False


def test_index_azure_search_on_approved():
    from shared.config.settings import Settings
    from shared.rag.approved_indexing import index_approved_recommendation

    request_id = uuid4()
    rec = SimpleNamespace(
        request_id=request_id,
        lifecycle_status="APPROVED",
        request_log_request_id=None,
        workspace_id="ws-1",
        recommendation={"rationale": "resize", "job_run_ingest": {"job_type": "ETL"}},
        explanation="explanation",
        pattern_analysis="patterns",
        comparison=None,
        job_id="job-1",
        job_run_id="run-1",
        reason_codes=[],
    )
    settings = Settings(
        _env_file=None,
        vector_retrieval_backend="azure_search",
        azure_search_endpoint="https://search.example.net",
        azure_search_api_key="key",
    )
    search = MagicMock()
    search.index_approved_document.return_value = True

    with patch("shared.rag.approved_indexing.DATABASE_AVAILABLE", True):
        with patch("shared.rag.approved_indexing.get_database_session") as mock_session:
            mock_session.return_value.query.return_value.filter.return_value.first.return_value = (
                rec
            )
            with patch(
                "shared.rag.approved_indexing.resolve_rag_settings_for_history",
                return_value=settings,
            ):
                with patch(
                    "AI.src.core.llm.azure_search_service.create_search_service",
                    return_value=search,
                ):
                    assert index_approved_recommendation(request_id) is True
                    search.index_approved_document.assert_called_once()
