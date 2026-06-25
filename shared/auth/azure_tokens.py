"""Azure AD access tokens via DefaultAzureCredential (az login, Managed Identity, etc.)."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

# Azure Databricks first-party app (same resource as `az account get-access-token --resource …`)
DATABRICKS_AAD_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

# Azure OpenAI / Cognitive Services
AZURE_OPENAI_AAD_SCOPE = "https://cognitiveservices.azure.com/.default"

# Azure AI Search
AZURE_SEARCH_AAD_SCOPE = "https://search.azure.com/.default"


@lru_cache(maxsize=1)
def _default_credential():
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def get_default_azure_credential():
    """Return a shared DefaultAzureCredential (az login, Managed Identity, etc.)."""
    return _default_credential()


def get_azure_access_token(scope: str) -> str:
    """Return a fresh Azure AD access token for the given scope."""
    token = _default_credential().get_token(scope)
    return token.token


def azure_token_provider(scope: str) -> Callable[[], str]:
    """Build a zero-arg callable that returns a token (refreshed on each call)."""

    def provider() -> str:
        return get_azure_access_token(scope)

    return provider
