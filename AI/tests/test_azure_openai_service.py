"""Unit tests for Azure OpenAI token resolution (no live Azure OpenAI)."""

from unittest.mock import patch

import pytest


@pytest.fixture
def openai_module():
    from AI.src.core.llm import azure_openai_service as mod

    return mod


def test_token_provider_fetches_and_caches_in_settings(openai_module, monkeypatch):
    monkeypatch.setattr(openai_module.settings, "azure_openai_access_token", None, raising=False)
    with patch(
        "shared.auth.azure_tokens.get_azure_access_token",
        return_value="mi-openai-token",
    ) as get_token:
        provider = openai_module._build_settings_cached_token_provider()
        assert provider() == "mi-openai-token"
        assert provider() == "mi-openai-token"
    get_token.assert_called_once()
    assert openai_module.settings.azure_openai_access_token == "mi-openai-token"


def test_token_provider_reuses_existing_settings_token(openai_module, monkeypatch):
    monkeypatch.setattr(
        openai_module.settings,
        "azure_openai_access_token",
        "from-env",
        raising=False,
    )
    with patch("shared.auth.azure_tokens.get_azure_access_token") as get_token:
        provider = openai_module._build_settings_cached_token_provider()
        assert provider() == "from-env"
        assert provider() == "from-env"
    get_token.assert_not_called()
