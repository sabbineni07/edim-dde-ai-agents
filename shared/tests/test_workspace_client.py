"""Tests for Databricks workspace client resolution."""

from unittest.mock import MagicMock, patch

import pytest

from shared.databricks.workspace_client import (
    databricks_workspace_host_from_settings,
    get_workspace_client,
    require_workspace_host_for_volume,
    resolve_databricks_workspace_host,
)


def test_resolve_host_from_server_hostname():
    assert (
        resolve_databricks_workspace_host(databricks_server_hostname="adb.example.net")
        == "https://adb.example.net"
    )


def test_resolve_host_prefers_explicit_host():
    assert (
        resolve_databricks_workspace_host(
            databricks_host="https://custom.example",
            databricks_server_hostname="adb.example.net",
        )
        == "https://custom.example"
    )


def test_host_from_settings_object():
    class _Cfg:
        databricks_server_hostname = "adb.example.net"

    assert databricks_workspace_host_from_settings(_Cfg()) == "https://adb.example.net"


def test_require_workspace_host_raises_without_config():
    with patch(
        "shared.databricks.workspace_client.is_databricks_app_runtime",
        return_value=False,
    ):
        with patch(
            "shared.databricks.workspace_client.databricks_workspace_host_from_settings",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="workspace host"):
                require_workspace_host_for_volume()


def test_get_workspace_client_uses_resolved_host():
    with patch(
        "shared.databricks.workspace_client.is_databricks_app_runtime",
        return_value=False,
    ):
        with patch("shared.databricks.workspace_client._workspace_client_cls") as cls:
            wc = MagicMock()
            cls.return_value = wc
            get_workspace_client(databricks_server_hostname="adb.example.net")
            wc.assert_called_once()
            assert wc.call_args.kwargs["host"] == "https://adb.example.net"
