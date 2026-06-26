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


def test_build_agent_runtime_deps_uses_workspace_foundry_without_platform_env(monkeypatch):
    """Workspace connection endpoint must work without AZURE_OPENAI_ENDPOINT in .env."""
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("USE_MOCK_LLM", "false")
    reset_settings_cache()

    from AI.src.agents.dbx_cluster_tuning_agent.deps import build_agent_runtime_deps

    settings = get_agent_settings(
        "dbx_cluster_tuning_agent",
        overrides={
            "vector_retrieval_backend": "none",
            "azure_openai_endpoint": "https://workspace-test.openai.azure.com",
            "azure_openai_deployment_name": "gpt-4o",
        },
    )
    deps = build_agent_runtime_deps(settings)
    assert deps["sizing_chain"].llm is not None
    assert deps["explanation_chain"].llm is not None
