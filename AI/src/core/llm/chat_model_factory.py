"""Build ChatOpenAI instances for Azure AI Foundry (OpenAI v1 API)."""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from shared.auth.azure_tokens import AZURE_FOUNDRY_AAD_SCOPE, get_azure_access_token
from shared.azure.endpoint_resolver import resolve_openai_v1_base_url
from shared.config.llm_sampling import ChainKind, resolve_llm_sampling
from shared.config.settings import Settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _token_provider_for_settings(cfg: Settings):
    def token_provider() -> str:
        token = (cfg.azure_openai_access_token or "").strip()
        if not token:
            token = get_azure_access_token(AZURE_FOUNDRY_AAD_SCOPE)
            cfg.azure_openai_access_token = token
        return token

    return token_provider


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
