"""Build ChatOpenAI instances for Azure AI Foundry (OpenAI v1 API)."""

from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from shared.auth.foundry_tokens import foundry_token_provider
from shared.azure.endpoint_resolver import resolve_openai_v1_base_url
from shared.config.llm_sampling import ChainKind, resolve_llm_sampling
from shared.config.settings import Settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _token_provider_for_settings(cfg: Settings):
    return foundry_token_provider(cfg)


def can_create_chat_model(cfg: Settings) -> bool:
    return bool((cfg.azure_openai_endpoint or "").strip())


def create_chat_model(cfg: Settings, *, chain: ChainKind = "default") -> BaseChatModel:
    """Create a chat model for the given settings bundle and chain sampling profile."""
    base_url = resolve_openai_v1_base_url((cfg.azure_openai_endpoint or "").strip())
    model = cfg.azure_openai_deployment_name or cfg.default_model_name or "gpt-4o"
    temperature, top_p = resolve_llm_sampling(cfg, chain)
    api_key = (cfg.azure_openai_api_key or "").strip()

    common = {
        "model": model,
        "base_url": base_url,
        "temperature": temperature,
        "top_p": top_p,
    }

    if api_key:
        llm = ChatOpenAI(api_key=api_key, **common)
    else:
        llm = ChatOpenAI(api_key=_token_provider_for_settings(cfg), **common)

    logger.debug(
        "foundry_chat_model_created",
        chain=chain,
        model=model,
        base_url=base_url,
        temperature=temperature,
        top_p=top_p,
    )
    return llm


def resolve_chain_llm(
    settings: Settings,
    *,
    chain: ChainKind = "default",
    llm_provider=None,
) -> BaseChatModel:
    """Pick chat model: workspace/agent Foundry → platform Foundry → mock (dev only).

    Order:
    1. ``azure_openai_endpoint`` on effective agent/workspace settings
    2. ``azure_openai_endpoint`` on platform settings
    3. ``USE_MOCK_LLM=true`` → mock LLM
    4. Else platform Foundry provider (raises when not configured)
    """
    from AI.src.core.platform import get_llm_provider, use_mock_llm
    from shared.config.loader import get_platform_settings

    if can_create_chat_model(settings):
        return create_chat_model(settings, chain=chain)

    platform = get_platform_settings()
    if can_create_chat_model(platform):
        return create_chat_model(platform, chain=chain)

    if use_mock_llm():
        provider = llm_provider or get_llm_provider()
        return provider.get_llm(chain)

    provider = llm_provider or get_llm_provider()
    return provider.get_llm(chain)
