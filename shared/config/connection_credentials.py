"""Optional dev-only secret overrides from process environment.

Production auth uses Azure identity at runtime (DefaultAzureCredential / Managed Identity).
Secrets are never stored in the database or UI.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict
from uuid import UUID


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
    """Return flat Settings secret fields only when global dev env vars are set.

    When empty, clients obtain tokens at runtime via Azure identity.
    """
    _ = connection_id, config  # reserved for future per-connection overrides
    out: Dict[str, Any] = {}

    if connection_type == "databricks":
        token = _env_first("DATABRICKS_TOKEN")
        if token:
            out["databricks_token"] = token

    elif connection_type == "ai_foundry":
        api_key = _env_first("AZURE_OPENAI_API_KEY")
        access = _env_first("AZURE_OPENAI_ACCESS_TOKEN")
        if api_key:
            out["azure_openai_api_key"] = api_key
        if access:
            out["azure_openai_access_token"] = access

    elif connection_type == "ai_search":
        key = _env_first("AZURE_SEARCH_API_KEY")
        if key:
            out["azure_search_api_key"] = key

    return out


def mask_config_for_response(config: Dict[str, Any]) -> Dict[str, Any]:
    """Strip any accidental secret-like keys from stored config before API response."""
    secret_re = re.compile(r"(token|api_key|password|secret|access_token)", re.I)
    return {k: v for k, v in (config or {}).items() if not secret_re.search(k)}
