"""Embedding clients from resolved Settings bundles (OpenAI v1 / Foundry)."""

from __future__ import annotations

from typing import Any

from langchain_openai import OpenAIEmbeddings

from shared.auth.azure_tokens import AZURE_FOUNDRY_AAD_SCOPE, get_azure_access_token
from shared.azure.endpoint_resolver import resolve_openai_v1_base_url
from shared.config.settings import Settings


def embeddings_from_settings(settings: Settings) -> Any:
    """Return LangChain embeddings for the given settings (API key or Azure AD)."""
    base_url = resolve_openai_v1_base_url((settings.azure_openai_endpoint or "").strip())
    model = settings.azure_openai_embedding_deployment or "text-embedding-3-small"
    api_key = (settings.azure_openai_api_key or "").strip()

    if api_key:
        return OpenAIEmbeddings(model=model, base_url=base_url, api_key=api_key)

    token = (settings.azure_openai_access_token or "").strip() or get_azure_access_token(
        AZURE_FOUNDRY_AAD_SCOPE
    )
    return OpenAIEmbeddings(model=model, base_url=base_url, api_key=token)
