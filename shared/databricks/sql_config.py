"""Normalize Databricks SQL warehouse connection settings for collectors."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping, Optional

_WAREHOUSE_ID_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)


def strip_databricks_hostname(host: str) -> str:
    """Return ``adb-….azuredatabricks.net`` without a URL scheme or trailing slash."""
    raw = (host or "").strip()
    if raw.startswith("https://"):
        raw = raw[8:]
    elif raw.startswith("http://"):
        raw = raw[7:]
    return raw.rstrip("/")


def normalize_sql_warehouse_http_path(http_path: Optional[str]) -> str:
    """Accept ``/sql/1.0/warehouses/<id>`` or a bare warehouse id (Apps ``valueFrom``)."""
    raw = (http_path or "").strip()
    if not raw:
        raw = (
            os.environ.get("DATABRICKS_HTTP_PATH") or os.environ.get("SQL_WAREHOUSE_ID") or ""
        ).strip()
    if not raw:
        return ""
    if raw.startswith("/sql/"):
        return raw
    if _WAREHOUSE_ID_RE.match(raw) or "/" not in raw:
        return f"/sql/1.0/warehouses/{raw}"
    return raw


def normalize_databricks_sql_config(
    config: Optional[Mapping[str, Any]] = None,
    *,
    databricks_host: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
    databricks_http_path: Optional[str] = None,
) -> dict[str, str]:
    """Merge connection config with Databricks App env fallbacks."""
    cfg = dict(config or {})
    hostname = strip_databricks_hostname(
        str(cfg.get("databricks_server_hostname") or databricks_server_hostname or "")
    )
    http_path = normalize_sql_warehouse_http_path(
        str(cfg.get("databricks_http_path") or databricks_http_path or "")
    )

    if not hostname:
        for candidate in (
            databricks_host,
            os.environ.get("DATABRICKS_HOST"),
            os.environ.get("DATABRICKS_SERVER_HOSTNAME"),
        ):
            if candidate:
                hostname = strip_databricks_hostname(str(candidate))
                break
        if not hostname:
            try:
                from shared.config.settings import settings

                hostname = strip_databricks_hostname(
                    str(settings.databricks_server_hostname or settings.databricks_host or "")
                )
            except Exception:
                pass

    return {
        "databricks_server_hostname": hostname,
        "databricks_http_path": http_path,
    }


def require_databricks_sql_config(
    config: Optional[Mapping[str, Any]] = None,
    **kwargs: Any,
) -> dict[str, str]:
    """Return normalized SQL config or raise with an actionable message."""
    normalized = normalize_databricks_sql_config(config, **kwargs)
    hostname = normalized["databricks_server_hostname"]
    http_path = normalized["databricks_http_path"]
    if not hostname:
        raise ValueError(
            "Databricks SQL warehouse hostname is missing. Set server hostname on the "
            "environment metrics connection, or rely on DATABRICKS_HOST on Databricks Apps."
        )
    if not http_path:
        raise ValueError(
            "Databricks SQL warehouse HTTP path is missing. Set HTTP path to "
            "/sql/1.0/warehouses/<id> on the metrics connection, or bind sql-warehouse "
            "via valueFrom in app.yaml."
        )
    return normalized
