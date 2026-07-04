"""Unit tests for Databricks token resolution (no live Databricks)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def collector_module():
    from DE.src.collectors import databricks_collector as mod

    return mod


def test_connection_params_use_env_token_when_set(collector_module, monkeypatch):
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_token",
        "from-env",
        raising=False,
    )
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_server_hostname",
        "adb.example.azuredatabricks.net",
        raising=False,
    )
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_http_path",
        "/sql/1.0/warehouses/x",
        raising=False,
    )
    collector = collector_module.DatabricksCollector()
    params = collector._connection_params()
    assert params["access_token"] == "from-env"


def test_connection_params_use_azure_identity_when_env_unset(collector_module, monkeypatch):
    monkeypatch.setattr(collector_module.settings, "databricks_token", None, raising=False)
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_server_hostname",
        "adb.example.azuredatabricks.net",
        raising=False,
    )
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_http_path",
        "/sql/1.0/warehouses/x",
        raising=False,
    )
    with patch(
        "shared.auth.databricks_tokens.get_app_service_principal_token",
        return_value=None,
    ):
        with patch(
            "shared.auth.databricks_tokens.get_azure_access_token",
            return_value="mi-token",
        ) as get_token:
            collector = collector_module.DatabricksCollector()
            params = collector._connection_params()
    get_token.assert_called_once()
    assert params["access_token"] == "mi-token"


def test_connection_params_use_request_scoped_user_token(collector_module, monkeypatch):
    monkeypatch.setattr(collector_module.settings, "databricks_token", "from-env", raising=False)
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_server_hostname",
        "adb.example.azuredatabricks.net",
        raising=False,
    )
    monkeypatch.setattr(
        collector_module.settings,
        "databricks_http_path",
        "/sql/1.0/warehouses/x",
        raising=False,
    )
    from shared.auth.databricks_tokens import (
        reset_request_databricks_token,
        set_request_databricks_token,
    )

    ctx = set_request_databricks_token("user-forwarded-token")
    try:
        collector = collector_module.DatabricksCollector()
        params = collector._connection_params()
        assert params["access_token"] == "user-forwarded-token"
    finally:
        reset_request_databricks_token(ctx)
