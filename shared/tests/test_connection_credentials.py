import os
from uuid import uuid4

from shared.config.connection_credentials import resolve_connection_secrets


def test_resolve_secrets_empty_without_env(monkeypatch):
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    secrets = resolve_connection_secrets("databricks", uuid4(), {})
    assert secrets == {}


def test_resolve_secrets_global_dev_override(monkeypatch):
    monkeypatch.setenv("DATABRICKS_TOKEN", "dev-token")
    secrets = resolve_connection_secrets("databricks", uuid4(), {})
    assert secrets["databricks_token"] == "dev-token"
