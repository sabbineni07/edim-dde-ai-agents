"""Resolve connection secrets from .env; omit when absent so clients use Managed Identity."""

from __future__ import annotations

import os
import re
from typing import Any, Dict
from uuid import UUID


def default_credential_env_prefix(connection_id: UUID) -> str:
    compact = str(connection_id).replace("-", "").upper()
    return f"CONN_{compact}_"


def _prefix(config: Dict[str, Any], connection_id: UUID) -> str:
    raw = config.get("credential_env_prefix")
    if raw and str(raw).strip():
        p = str(raw).strip()
        return p if p.endswith("_") else f"{p}_"
    return default_credential_env_prefix(connection_id)


def _env_first(*keys: str) -> str | None:
    for k in keys:
        if not k:
            continue
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def resolve_connection_secrets(
    connection_type: str,
    connection_id: UUID,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Return flat Settings secret fields when present in .env; empty dict → use MI in clients."""
    prefix = _prefix(config, connection_id)
    out: Dict[str, Any] = {}

    if connection_type == "databricks":
        token = _env_first(f"{prefix}DATABRICKS_TOKEN", "DATABRICKS_TOKEN")
        if token:
            out["databricks_token"] = token

    elif connection_type == "ai_foundry":
        api_key = _env_first(f"{prefix}AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_KEY")
        access = _env_first(f"{prefix}AZURE_OPENAI_ACCESS_TOKEN", "AZURE_OPENAI_ACCESS_TOKEN")
        if api_key:
            out["azure_openai_api_key"] = api_key
        if access:
            out["azure_openai_access_token"] = access

    elif connection_type == "ai_search":
        key = _env_first(f"{prefix}AZURE_SEARCH_API_KEY", "AZURE_SEARCH_API_KEY")
        if key:
            out["azure_search_api_key"] = key

    return out


def mask_config_for_response(config: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any accidental secret-like keys from stored config before API response."""
    secret_re = re.compile(r"(token|api_key|password|secret|access_token)", re.I)
    return {k: v for k, v in (config or {}).items() if not secret_re.search(k)}
