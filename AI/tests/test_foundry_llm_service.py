"""Unit tests for Foundry LLM token resolution (no live Azure calls)."""

from unittest.mock import patch

import pytest


@pytest.fixture
def foundry_module():
    from AI.src.core.llm import foundry_llm_service as mod

    return mod


def test_token_provider_fetches_and_caches_in_settings(foundry_module, monkeypatch):
    monkeypatch.setattr(foundry_module.settings, "azure_openai_access_token", None, raising=False)
    with patch(
        "shared.auth.azure_tokens.get_azure_access_token",
        return_value="mi-foundry-token",
    ) as get_token:
        provider = foundry_module._build_settings_cached_token_provider(foundry_module.settings)
        assert provider() == "mi-foundry-token"
        assert provider() == "mi-foundry-token"
    get_token.assert_called_once()
    assert foundry_module.settings.azure_openai_access_token == "mi-foundry-token"


def test_token_provider_reuses_existing_settings_token(foundry_module, monkeypatch):
    monkeypatch.setattr(
        foundry_module.settings,
        "azure_openai_access_token",
        "from-env",
        raising=False,
    )
    with patch("shared.auth.azure_tokens.get_azure_access_token") as get_token:
        provider = foundry_module._build_settings_cached_token_provider(foundry_module.settings)
        assert provider() == "from-env"
        assert provider() == "from-env"
    get_token.assert_not_called()
