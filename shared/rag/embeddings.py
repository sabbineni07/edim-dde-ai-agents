"""Embedding clients from resolved Settings bundles."""

from __future__ import annotations

from typing import Any

from shared.config.settings import Settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_azure_endpoint(endpoint: str) -> str:
    if "/api/projects/" in endpoint:
        return endpoint.split("/api/projects/")[0].rstrip("/")
    return endpoint.rstrip("/")


def embeddings_from_settings(settings: Settings) -> Any:
    """Return LangChain embeddings for the given settings (API key or Azure AD)."""
    from langchain_openai import AzureOpenAIEmbeddings

    endpoint = _normalize_azure_endpoint((settings.azure_openai_endpoint or "").strip())
    if not endpoint:
        raise ValueError("Azure OpenAI endpoint not configured for embeddings")

    api_version = settings.azure_openai_api_version or "2024-05-01-preview"
    deployment = settings.azure_openai_embedding_deployment or "text-embedding-3-small"
    api_key = (settings.azure_openai_api_key or "").strip()

    if api_key:
        return AzureOpenAIEmbeddings(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            azure_deployment=deployment,
        )

    from shared.auth.azure_tokens import AZURE_OPENAI_AAD_SCOPE, get_azure_access_token

    token = (settings.azure_openai_access_token or "").strip() or get_azure_access_token(
        AZURE_OPENAI_AAD_SCOPE
    )
    return AzureOpenAIEmbeddings(
        azure_endpoint=endpoint,
        azure_ad_token=token,
        api_version=api_version,
        azure_deployment=deployment,
    )
