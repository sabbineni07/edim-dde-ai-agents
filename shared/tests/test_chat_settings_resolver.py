"""Tests for connection-scoped chat settings resolution."""

from uuid import uuid4

import pytest

from shared.config.chat_settings_resolver import resolve_chat_settings
from shared.services.environment_connection_service import EnvironmentConnectionService


@pytest.fixture
def env_with_chat_connections(monkeypatch):
    monkeypatch.setenv("USE_POSTGRES", "false")
    from shared.services import environment_connection_service as ecs

    ecs._MEM_CONNECTIONS.clear()

    svc = EnvironmentConnectionService()
    llm = svc.create_connection(
        environment_id="dim_dev",
        name="Test Foundry",
        connection_type="ai_foundry",
        purpose="llm",
        config={
            "azure_openai_endpoint": "https://test.services.ai.azure.com",
            "azure_openai_deployment_name": "gpt-4o",
        },
        validate=False,
    )
    rag = svc.create_connection(
        environment_id="dim_dev",
        name="Test Search",
        connection_type="ai_search",
        purpose="rag",
        config={
            "azure_search_endpoint": "https://test.search.windows.net",
            "azure_search_index_name": "rec-index",
        },
        validate=False,
    )
    return llm, rag


def test_resolve_chat_settings_llm_only(env_with_chat_connections):
    llm, _ = env_with_chat_connections
    settings, meta = resolve_chat_settings(
        environment_id="dim_dev",
        llm_connection_id=llm.id,
        rag_connection_id=None,
    )
    assert settings.azure_openai_endpoint == "https://test.services.ai.azure.com"
    assert settings.vector_retrieval_backend == "none"
    assert meta["llm_connection_id"] == str(llm.id)
    assert meta["rag_connection_id"] is None


def test_resolve_chat_settings_with_rag(env_with_chat_connections):
    llm, rag = env_with_chat_connections
    settings, meta = resolve_chat_settings(
        environment_id="dim_dev",
        llm_connection_id=llm.id,
        rag_connection_id=rag.id,
    )
    assert settings.vector_retrieval_backend == "azure_search"
    assert settings.azure_search_index_name == "rec-index"
    assert meta["rag_connection_id"] == str(rag.id)


def test_resolve_chat_settings_wrong_environment(env_with_chat_connections):
    llm, _ = env_with_chat_connections
    with pytest.raises(ValueError, match="does not belong"):
        resolve_chat_settings(
            environment_id="other_env",
            llm_connection_id=llm.id,
        )


def test_resolve_chat_settings_missing_connection():
    with pytest.raises(LookupError):
        resolve_chat_settings(
            environment_id="dim_dev",
            llm_connection_id=uuid4(),
        )
