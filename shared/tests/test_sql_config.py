"""Tests for Databricks SQL warehouse config normalization."""

import os
from unittest.mock import patch

import pytest

from shared.databricks.sql_config import (
    normalize_databricks_sql_config,
    normalize_sql_warehouse_http_path,
    require_databricks_sql_config,
    strip_databricks_hostname,
)


def test_strip_databricks_hostname():
    assert (
        strip_databricks_hostname("https://adb-1.azuredatabricks.net/")
        == "adb-1.azuredatabricks.net"
    )


def test_normalize_http_path_bare_warehouse_id():
    assert (
        normalize_sql_warehouse_http_path("a1b2c3d4e5f67890")
        == "/sql/1.0/warehouses/a1b2c3d4e5f67890"
    )


def test_normalize_http_path_keeps_full_path():
    path = "/sql/1.0/warehouses/a1b2c3d4e5f67890"
    assert normalize_sql_warehouse_http_path(path) == path


def test_normalize_from_app_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-1.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "abc123def4567890")
    cfg = normalize_databricks_sql_config({})
    assert cfg["databricks_server_hostname"] == "adb-1.azuredatabricks.net"
    assert cfg["databricks_http_path"] == "/sql/1.0/warehouses/abc123def4567890"


def test_require_config_raises_without_host():
    with patch(
        "shared.databricks.sql_config.normalize_databricks_sql_config",
        return_value={"databricks_server_hostname": "", "databricks_http_path": "/sql/x"},
    ):
        with pytest.raises(ValueError, match="hostname"):
            require_databricks_sql_config({})
