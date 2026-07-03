"""Databricks SQL access token resolution for Apps, Azure identity, and PAT."""

from __future__ import annotations

import os
import re
import time
from contextvars import ContextVar, Token
from typing import Any, Mapping, Optional

from shared.auth.azure_tokens import DATABRICKS_AAD_SCOPE, get_azure_access_token
from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_FORWARDED_TOKEN_HEADERS = (
    "x-forwarded-access-token",
    "X-Forwarded-Access-Token",
)

_STUB_AUTH_RE = re.compile(r"^Bearer\s+stub-token-", re.IGNORECASE)

_request_databricks_token: ContextVar[Optional[str]] = ContextVar(
    "request_databricks_token", default=None
)

_m2m_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def is_stub_authorization(value: Optional[str]) -> bool:
    """True for Angular local stub login tokens (not valid on Databricks)."""
    return bool(value and _STUB_AUTH_RE.match(value.strip()))


def _header_value(headers: Mapping[str, Any], name: str) -> Optional[str]:
    key = name.lower()
    for header_name, value in headers.items():
        if str(header_name).lower() == key:
            if isinstance(value, (list, tuple)):
                return str(value[0]).strip() if value else None
            return str(value).strip() if value is not None else None
    return None


def extract_forwarded_databricks_token(headers: Mapping[str, Any]) -> Optional[str]:
    """Read a user OAuth token from Databricks Apps gateway or proxy headers."""
    for name in _FORWARDED_TOKEN_HEADERS:
        token = _header_value(headers, name)
        if token:
            return token

    authorization = _header_value(headers, "authorization")
    if authorization and not is_stub_authorization(authorization):
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            return token or None
    return None


def set_request_databricks_token(token: Optional[str]) -> Token:
    return _request_databricks_token.set((token or "").strip() or None)


def reset_request_databricks_token(ctx: Token) -> None:
    _request_databricks_token.reset(ctx)


def get_request_databricks_token() -> Optional[str]:
    return _request_databricks_token.get()


def _fetch_m2m_token() -> Optional[str]:
    """OAuth client-credentials token for the Databricks App service principal."""
    now = time.time()
    cached = _m2m_cache.get("token")
    expires_at = float(_m2m_cache.get("expires_at") or 0.0)
    if cached and expires_at > now + 60:
        return str(cached)

    host = (os.environ.get("DATABRICKS_HOST") or settings.databricks_host or "").rstrip("/")
    client_id = (
        os.environ.get("DATABRICKS_CLIENT_ID") or settings.databricks_client_id or ""
    ).strip()
    client_secret = (
        os.environ.get("DATABRICKS_CLIENT_SECRET") or settings.databricks_client_secret or ""
    ).strip()
    if not (host and client_id and client_secret):
        return None

    import base64
    import json
    import urllib.error
    import urllib.request

    token_url = f"{host}/oidc/v1/token"
    body = "grant_type=client_credentials&scope=all-apis".encode("utf-8")
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        token_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {basic}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
        logger.warning("databricks_m2m_token_failed", error=str(e))
        return None

    token = (payload.get("access_token") or "").strip()
    if not token:
        return None
    _m2m_cache["token"] = token
    _m2m_cache["expires_at"] = now + float(payload.get("expires_in") or 3600)
    return token


def get_app_service_principal_token() -> Optional[str]:
    """Token for the Databricks App service principal (Apps runtime or SP env vars)."""
    try:
        from shared.database.connection import _get_workspace_client

        client = _get_workspace_client()
        headers = client.config.authenticate()
        authorization = headers.get("Authorization") or headers.get("authorization") or ""
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            if token:
                logger.debug("databricks_token_from_workspace_client")
                return token
    except Exception as e:
        logger.debug("databricks_workspace_client_token_unavailable", error=str(e))

    token = _fetch_m2m_token()
    if token:
        logger.debug("databricks_token_from_m2m")
    return token


def get_azure_identity_databricks_token() -> Optional[str]:
    """Azure AD token for Databricks (az login, Managed Identity, etc.)."""
    try:
        return get_azure_access_token(DATABRICKS_AAD_SCOPE)
    except Exception as e:
        logger.warning(
            "databricks_azure_identity_token_unavailable",
            error=str(e),
            hint="Run az login or assign Managed Identity with Databricks access.",
        )
        return None


def resolve_databricks_sql_token(
    request: Any = None,
    *,
    headers: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Resolve a Databricks SQL warehouse access token.

    Priority:
    1. Request-scoped token (set by middleware from forwarded user OAuth)
    2. Explicit headers (``X-Forwarded-Access-Token`` or non-stub ``Authorization``)
    3. ``DATABRICKS_TOKEN`` / settings
    4. Databricks App service principal (``WorkspaceClient`` / M2M)
    5. ``DefaultAzureCredential`` via Azure AD scope
    """
    scoped = get_request_databricks_token()
    if scoped:
        return scoped

    header_map = headers
    if header_map is None and request is not None:
        header_map = getattr(request, "headers", None)
    if header_map is not None:
        forwarded = extract_forwarded_databricks_token(header_map)
        if forwarded:
            return forwarded

    env_token = (settings.databricks_token or "").strip()
    if env_token:
        return env_token

    app_token = get_app_service_principal_token()
    if app_token:
        return app_token

    from shared.databricks.workspace_client import is_databricks_app_runtime

    if is_databricks_app_runtime():
        logger.warning(
            "databricks_app_sql_token_unavailable",
            hint="Attach sql-warehouse app resource and redeploy.",
        )
        return None

    return get_azure_identity_databricks_token()


def resolve_databricks_sql_access_token(
    request: Any = None,
    *,
    headers: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Alias used by collectors; see :func:`resolve_databricks_sql_token`."""
    return resolve_databricks_sql_token(request, headers=headers)
