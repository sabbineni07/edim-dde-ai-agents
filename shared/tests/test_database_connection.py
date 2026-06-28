"""Tests for Postgres connection URL and backend branching."""

import pytest

from shared.config.loader import reset_settings_cache
from shared.database.connection import (
    get_database_url,
    postgres_backend,
    reset_database_connection,
    use_lakebase_oauth,
)


@pytest.fixture(autouse=True)
def _reset_connection_state():
    reset_settings_cache()
    reset_database_connection()
    yield
    reset_settings_cache()
    reset_database_connection()


def _set_local_postgres_env(monkeypatch):
    monkeypatch.setenv("USE_POSTGRES", "true")
    monkeypatch.setenv("POSTGRES_BACKEND", "local")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")
    monkeypatch.setenv("POSTGRES_DATABASE", "ai_agents")
    monkeypatch.setenv("POSTGRES_SSL_MODE", "prefer")


def _set_lakebase_postgres_env(monkeypatch):
    monkeypatch.setenv("USE_POSTGRES", "true")
    monkeypatch.setenv("POSTGRES_BACKEND", "lakebase")
    monkeypatch.setenv("POSTGRES_HOST", "ep-abc-123.databricks.com")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_USER", "me@example.com")
    monkeypatch.setenv("POSTGRES_DATABASE", "databricks_postgres")
    monkeypatch.setenv("POSTGRES_SSL_MODE", "require")
    monkeypatch.setenv(
        "POSTGRES_LAKEBASE_ENDPOINT",
        "projects/my-project/branches/production/endpoints/primary",
    )


def test_postgres_backend_defaults_to_local(monkeypatch):
    _set_local_postgres_env(monkeypatch)
    monkeypatch.delenv("POSTGRES_BACKEND", raising=False)
    reset_settings_cache()
    assert postgres_backend() == "local"
    assert use_lakebase_oauth() is False


def test_get_database_url_local_unchanged(monkeypatch):
    _set_local_postgres_env(monkeypatch)
    reset_settings_cache()

    url = get_database_url()

    assert url.startswith("postgresql://postgres:postgres@localhost:5432/ai_agents")
    assert "sslmode=prefer" in url
    assert "+psycopg" not in url


def test_get_database_url_local_ssl_disabled(monkeypatch):
    _set_local_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_SSL_MODE", "disable")
    reset_settings_cache()

    url = get_database_url()

    assert url == "postgresql://postgres:postgres@localhost:5432/ai_agents"
    assert "sslmode" not in url


def test_get_database_url_lakebase_uses_psycopg_without_password(monkeypatch):
    _set_lakebase_postgres_env(monkeypatch)
    reset_settings_cache()

    url = get_database_url()

    assert url.startswith("postgresql+psycopg://me%40example.com:@")
    assert "ep-abc-123.databricks.com:5432/databricks_postgres" in url
    assert "sslmode=require" in url
    assert use_lakebase_oauth() is True


def test_get_database_url_lakebase_requires_endpoint(monkeypatch):
    _set_lakebase_postgres_env(monkeypatch)
    monkeypatch.delenv("POSTGRES_LAKEBASE_ENDPOINT", raising=False)
    reset_settings_cache()

    with pytest.raises(ValueError, match="POSTGRES_LAKEBASE_ENDPOINT"):
        get_database_url()


def test_get_database_url_lakebase_requires_host(monkeypatch):
    _set_lakebase_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_HOST", "")
    reset_settings_cache()

    with pytest.raises(ValueError, match="POSTGRES_HOST"):
        get_database_url()
