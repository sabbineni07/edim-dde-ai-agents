"""Foundry token resolution with Databricks service-credential first, Azure fallback.

Unity Catalog service credentials via ``dbutils`` are for cluster/job/notebook runtimes.
They are **not** supported on Databricks Apps — Apps skip that path and use Azure identity
(``DATABRICKS_CLIENT_ID`` + ``DATABRICKS_CLIENT_SECRET`` + ``AZURE_TENANT_ID``, or
``AZURE_CLIENT_*``, or ``DefaultAzureCredential``).
"""

from __future__ import annotations

import builtins
import os
from typing import Any, Optional

from shared.auth.azure_tokens import AZURE_FOUNDRY_AAD_SCOPE, get_azure_access_token
from shared.config.settings import Settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _is_databricks_app_runtime() -> bool:
    return bool(os.environ.get("DATABRICKS_APP_NAME"))


def _resolve_service_credential_name(cfg: Settings) -> str:
    explicit = (getattr(cfg, "databricks_service_credential_name", None) or "").strip()
    if explicit:
        return explicit
    return (os.environ.get("DATABRICKS_SERVICE_CREDENTIAL_NAME") or "").strip()


def _resolve_dbutils() -> Optional[Any]:
    dbutils_obj = getattr(builtins, "dbutils", None)
    if dbutils_obj is not None:
        return dbutils_obj

    try:
        from databricks.sdk.runtime import dbutils as runtime_dbutils

        return runtime_dbutils
    except Exception:
        return None


def _get_databricks_service_credential_provider(service_credential_name: str) -> Optional[Any]:
    dbutils_obj = _resolve_dbutils()
    if dbutils_obj is None:
        return None

    credentials_mod = getattr(dbutils_obj, "credentials", None)
    if credentials_mod is None:
        return None

    get_provider = getattr(credentials_mod, "getServiceCredentialsProvider", None)
    if not callable(get_provider):
        return None

    return get_provider(service_credential_name)


def get_foundry_access_token(cfg: Settings) -> str:
    """Resolve Foundry bearer token.

    Priority:
    1. ``settings.azure_openai_access_token`` when explicitly supplied.
    2. Databricks UC service credential (cluster/job/notebook only; skipped on Apps).
    3. Azure identity (App SP + ``AZURE_TENANT_ID``, ``AZURE_CLIENT_*``, or DefaultAzureCredential).
    """
    token = (cfg.azure_openai_access_token or "").strip()
    if token:
        return token

    service_credential_name = _resolve_service_credential_name(cfg)
    if service_credential_name and _is_databricks_app_runtime():
        logger.info(
            "foundry_dbx_service_credential_skipped_on_apps",
            service_credential_name=service_credential_name,
            hint=(
                "UC service credentials are not supported in Databricks Apps. "
                "Use App SP + AZURE_TENANT_ID + Foundry RBAC instead."
            ),
        )
    elif service_credential_name:
        try:
            provider = _get_databricks_service_credential_provider(service_credential_name)
            if provider is not None:
                token = provider.get_token(AZURE_FOUNDRY_AAD_SCOPE).token
                logger.info(
                    "foundry_token_from_databricks_service_credential",
                    service_credential_name=service_credential_name,
                )
                cfg.azure_openai_access_token = token
                return token
            logger.warning(
                "foundry_dbx_service_credential_unavailable",
                service_credential_name=service_credential_name,
            )
        except Exception as e:
            logger.warning(
                "foundry_dbx_service_credential_failed",
                service_credential_name=service_credential_name,
                error=str(e),
            )

    token = get_azure_access_token(AZURE_FOUNDRY_AAD_SCOPE)
    cfg.azure_openai_access_token = token
    logger.info("foundry_token_from_azure_identity")
    return token


def foundry_token_provider(cfg: Settings):
    """Return OpenAI-compatible token provider callable for Foundry."""

    def provider() -> str:
        return get_foundry_access_token(cfg)

    return provider
