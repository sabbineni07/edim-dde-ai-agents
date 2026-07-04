"""Tests for Databricks SQL token resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from shared.auth.databricks_tokens import (
    extract_forwarded_databricks_token,
    reset_request_databricks_token,
    resolve_databricks_sql_token,
    set_request_databricks_token,
)


def test_extract_forwarded_token_from_x_forwarded_header():
    headers = {"x-forwarded-access-token": "user-oauth-token"}
    assert extract_forwarded_databricks_token(headers) == "user-oauth-token"


def test_extract_forwarded_token_ignores_stub_authorization():
    headers = {"authorization": "Bearer stub-token-dev"}
    assert extract_forwarded_databricks_token(headers) is None


def test_extract_forwarded_token_from_authorization():
    headers = {"Authorization": "Bearer real-user-token"}
    assert extract_forwarded_databricks_token(headers) == "real-user-token"


def test_resolve_prefers_request_scoped_token():
    ctx = set_request_databricks_token("scoped-user-token")
    try:
        assert resolve_databricks_sql_token() == "scoped-user-token"
    finally:
        reset_request_databricks_token(ctx)


def test_resolve_falls_back_to_env_token(monkeypatch):
    monkeypatch.setattr(
        "shared.auth.databricks_tokens.settings.databricks_token",
        "pat-from-env",
        raising=False,
    )
    with patch("shared.auth.databricks_tokens.get_app_service_principal_token", return_value=None):
        assert resolve_databricks_sql_token() == "pat-from-env"


def test_resolve_falls_back_to_app_sp(monkeypatch):
    monkeypatch.setattr(
        "shared.auth.databricks_tokens.settings.databricks_token",
        None,
        raising=False,
    )
    with patch(
        "shared.auth.databricks_tokens.get_app_service_principal_token",
        return_value="app-sp-token",
    ):
        assert resolve_databricks_sql_token() == "app-sp-token"
