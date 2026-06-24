"""Tests for per-request agent runtime deps (RAG gating)."""

from unittest.mock import MagicMock

from AI.src.core.llm.azure_search_service import create_search_service
from shared.config.loader import get_agent_settings, reset_settings_cache


def test_create_search_service_off_when_rag_none():
    reset_settings_cache()
    settings = get_agent_settings(
        "dbx_cluster_tuning_agent",
        overrides={"vector_retrieval_backend": "none"},
    )
    assert create_search_service(settings) is None


def test_get_sizing_chain_rag_off_without_llm_init():
    reset_settings_cache()
    from AI.src.agents.dbx_cluster_tuning_agent.deps import get_sizing_chain

    settings = get_agent_settings(
        "dbx_cluster_tuning_agent",
        overrides={"vector_retrieval_backend": "none"},
    )
    mock_llm = MagicMock()
    chain = get_sizing_chain(settings=settings, llm_provider=mock_llm)
    assert chain.use_rag is False
