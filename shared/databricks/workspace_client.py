"""Databricks WorkspaceClient factory from resolved settings or platform defaults."""

from __future__ import annotations

import os
from typing import Any, Optional

from shared.utils.logging import get_logger

logger = get_logger(__name__)


def is_databricks_app_runtime() -> bool:
    return bool(os.environ.get("DATABRICKS_APP_NAME"))


def resolve_databricks_workspace_host(
    *,
    databricks_host: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> Optional[str]:
    """Return ``https://<workspace-host>`` for the Databricks REST / Files APIs."""
    host = (databricks_host or "").strip()
    if host:
        return host if host.startswith("http") else f"https://{host}"
    server_hostname = (databricks_server_hostname or "").strip()
    if server_hostname:
        return f"https://{server_hostname}"
    return None


def databricks_workspace_host_from_settings(settings: Any) -> Optional[str]:
    if settings is None:
        return None
    if isinstance(settings, dict):
        return resolve_databricks_workspace_host(
            databricks_host=settings.get("databricks_host"),
            databricks_server_hostname=settings.get("databricks_server_hostname"),
        )
    return resolve_databricks_workspace_host(
        databricks_host=getattr(settings, "databricks_host", None),
        databricks_server_hostname=getattr(settings, "databricks_server_hostname", None),
    )


def get_workspace_client(
    *,
    databricks_host: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
):
    """Build ``WorkspaceClient`` for UC volume Files API or other workspace calls."""
    from databricks.sdk import WorkspaceClient

    if is_databricks_app_runtime():
        return WorkspaceClient()

    kwargs: dict[str, Any] = {}
    host = resolve_databricks_workspace_host(
        databricks_host=databricks_host,
        databricks_server_hostname=databricks_server_hostname,
    )
    if not host:
        from shared.config.settings import settings as platform_settings

        host = databricks_workspace_host_from_settings(platform_settings)
    if host:
        kwargs["host"] = host

    from shared.config.settings import settings as platform_settings

    client_id = (platform_settings.databricks_client_id or "").strip()
    client_secret = (platform_settings.databricks_client_secret or "").strip()
    if client_id and client_secret:
        kwargs["client_id"] = client_id
        kwargs["client_secret"] = client_secret

    if not host and not is_databricks_app_runtime():
        logger.debug(
            "databricks_workspace_host_unset",
            hint="Bind a metrics dataset in an environment with a Databricks connection.",
        )
    return WorkspaceClient(**kwargs)


def get_workspace_client_for_settings(settings: Any):
    if settings is None:
        return get_workspace_client()
    if isinstance(settings, dict):
        return get_workspace_client(
            databricks_host=settings.get("databricks_host"),
            databricks_server_hostname=settings.get("databricks_server_hostname"),
        )
    return get_workspace_client(
        databricks_host=getattr(settings, "databricks_host", None),
        databricks_server_hostname=getattr(settings, "databricks_server_hostname", None),
    )


def require_workspace_host_for_volume(
    *,
    databricks_host: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> str:
    """Raise when UC volume sync needs a workspace host outside Databricks Apps."""
    if is_databricks_app_runtime():
        return ""
    host = resolve_databricks_workspace_host(
        databricks_host=databricks_host,
        databricks_server_hostname=databricks_server_hostname,
    )
    if not host:
        from shared.config.settings import settings as platform_settings

        host = databricks_workspace_host_from_settings(platform_settings)
    if not host:
        raise ValueError(
            "Databricks workspace host is required for Unity Catalog volume FAISS. "
            "Install the workspace agent in an environment with a Databricks metrics "
            "connection, or set DATABRICKS_HOST / DATABRICKS_SERVER_HOSTNAME for local dev."
        )
    return host
