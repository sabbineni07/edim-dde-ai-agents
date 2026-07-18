"""Tests for resolve_chain_llm priority (agent → platform → mock)."""

import os

import pytest

from AI.src.core.llm.chat_model_factory import resolve_chain_llm
from AI.src.core.platform import reset_platform_singletons
from shared.config.loader import reset_settings_cache
from shared.config.settings import Settings


@pytest.fixture(autouse=True)
def _reset_caches():
    reset_platform_singletons()
    reset_settings_cache()
    yield
    reset_platform_singletons()
    reset_settings_cache()


def test_resolve_chain_llm_prefers_agent_endpoint(monkeypatch):
    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    agent = Settings(_env_file=None, azure_openai_endpoint="https://agent.openai.azure.com/")
    platform = Settings(_env_file=None, azure_openai_endpoint="https://platform.openai.azure.com/")

    monkeypatch.setattr(
        "shared.config.loader.get_platform_settings",
        lambda: platform,
    )
    monkeypatch.setattr(
        "AI.src.core.llm.chat_model_factory.create_chat_model",
        lambda cfg, chain="default": f"model:{cfg.azure_openai_endpoint}:{chain}",
    )

    llm = resolve_chain_llm(agent, chain="sizing")
    assert llm == "model:https://agent.openai.azure.com/:sizing"


def test_resolve_chain_llm_falls_back_to_platform(monkeypatch):
    monkeypatch.delenv("USE_MOCK_LLM", raising=False)
    agent = Settings(_env_file=None)
    platform = Settings(_env_file=None, azure_openai_endpoint="https://platform.openai.azure.com/")

    monkeypatch.setattr(
        "shared.config.loader.get_platform_settings",
        lambda: platform,
    )
    monkeypatch.setattr(
        "AI.src.core.llm.chat_model_factory.create_chat_model",
        lambda cfg, chain="default": f"model:{cfg.azure_openai_endpoint}:{chain}",
    )

    llm = resolve_chain_llm(agent, chain="sizing")
    assert llm == "model:https://platform.openai.azure.com/:sizing"


def test_resolve_chain_llm_uses_mock_when_no_endpoint_and_mock_enabled(monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    agent = Settings(_env_file=None)
    platform = Settings(_env_file=None)

    monkeypatch.setattr(
        "shared.config.loader.get_platform_settings",
        lambda: platform,
    )

    llm = resolve_chain_llm(agent, chain="sizing")
    assert getattr(llm, "_llm_type", None) == "mock"
