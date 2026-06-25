"""Build AzureChatOpenAI instances from resolved Settings (sampling + auth)."""

from __future__ import annotations

from typing import Optional

from langchain_openai import AzureChatOpenAI

from shared.config.llm_sampling import ChainKind, resolve_llm_sampling
from shared.config.settings import Settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_azure_endpoint(endpoint: str) -> str:
    if "/api/projects/" in endpoint:
        return endpoint.split("/api/projects/")[0].rstrip("/")
    return endpoint.rstrip("/")


def _token_provider_for_settings(cfg: Settings):
    def token_provider() -> str:
        token = (cfg.azure_openai_access_token or "").strip()
        if not token:
            from shared.auth.azure_tokens import AZURE_OPENAI_AAD_SCOPE, get_azure_access_token

            token = get_azure_access_token(AZURE_OPENAI_AAD_SCOPE)
            cfg.azure_openai_access_token = token
        return token

    return token_provider


def can_create_chat_model(cfg: Settings) -> bool:
    return bool((cfg.azure_openai_endpoint or "").strip())


def create_azure_chat_model(cfg: Settings, *, chain: ChainKind = "default") -> AzureChatOpenAI:
    """Create a chat model for the given settings bundle and chain sampling profile."""
    endpoint = _normalize_azure_endpoint((cfg.azure_openai_endpoint or "").strip())
    if not endpoint:
        raise ValueError("Azure OpenAI endpoint not configured")

    temperature, top_p = resolve_llm_sampling(cfg, chain)
    api_version = cfg.azure_openai_api_version or "2024-05-01-preview"
    deployment = cfg.azure_openai_deployment_name or cfg.default_model_name or "gpt-4o"
    api_key = (cfg.azure_openai_api_key or "").strip()

    common = {
        "azure_endpoint": endpoint,
        "api_version": api_version,
        "azure_deployment": deployment,
        "temperature": temperature,
        "top_p": top_p,
    }

    if api_key:
        llm = AzureChatOpenAI(api_key=api_key, **common)
    else:
        llm = AzureChatOpenAI(
            azure_ad_token_provider=_token_provider_for_settings(cfg),
            **common,
        )

    logger.debug(
        "azure_chat_model_created",
        chain=chain,
        deployment=deployment,
        temperature=temperature,
        top_p=top_p,
    )
    return llm
