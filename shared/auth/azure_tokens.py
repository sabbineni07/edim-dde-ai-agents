"""Azure AD access tokens via DefaultAzureCredential (az login, Managed Identity, etc.)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Callable, Optional

from shared.ssl import configure_corporate_ssl

# Azure Databricks first-party app (same resource as `az account get-access-token --resource …`)
DATABRICKS_AAD_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

# Azure AI Foundry / OpenAI v1 (chat + embeddings)
AZURE_FOUNDRY_AAD_SCOPE = "https://ai.azure.com/.default"

# Azure AI Search
AZURE_SEARCH_AAD_SCOPE = "https://search.azure.com/.default"


def _env_first(*keys: str) -> Optional[str]:
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def _client_secret_credential_kwargs() -> Optional[dict[str, str]]:
    """Build ClientSecretCredential kwargs from AZURE_* or Databricks App SP env."""
    client_id = _env_first("AZURE_CLIENT_ID")
    client_secret = _env_first("AZURE_CLIENT_SECRET")
    tenant_id = _env_first("AZURE_TENANT_ID")

    if not client_id and os.environ.get("DATABRICKS_APP_NAME"):
        client_id = _env_first("DATABRICKS_CLIENT_ID")
        client_secret = _env_first("DATABRICKS_CLIENT_SECRET")

    if client_id and client_secret and tenant_id:
        return {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    return None


@lru_cache(maxsize=1)
def _default_credential():
    configure_corporate_ssl()
    secret_kwargs = _client_secret_credential_kwargs()
    if secret_kwargs:
        from azure.identity import ClientSecretCredential

        return ClientSecretCredential(**secret_kwargs)

    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


def get_default_azure_credential():
    """Return a shared Azure credential (SP secret, az login, Managed Identity, etc.)."""
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
