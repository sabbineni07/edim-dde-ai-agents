"""Tests for Postgres connection URL and backend branching."""

import pytest

from shared.config.loader import reset_settings_cache
from shared.database.connection import (
    _generate_lakebase_database_credential,
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


def test_get_database_url_lakebase_uses_psycopg2_without_password(monkeypatch):
    _set_lakebase_postgres_env(monkeypatch)
    reset_settings_cache()

    url = get_database_url()

    assert url.startswith("postgresql+psycopg2://me%40example.com:@")
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


def test_get_database_url_lakebase_reads_pghost_alias(monkeypatch):
    _set_lakebase_postgres_env(monkeypatch)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.setenv("PGHOST", "ep-apps.database.westus2.cloud.databricks.com")
    monkeypatch.setenv("PGUSER", "sp-client-id@apps")
    monkeypatch.setenv("PGDATABASE", "databricks_postgres")
    monkeypatch.setenv("PGSSLMODE", "require")
    monkeypatch.setenv(
        "POSTGRES_LAKEBASE_ENDPOINT",
        "projects/my-project/branches/production/endpoints/primary",
    )
    monkeypatch.setattr("shared.config.loader._env_file_usable", lambda: False)
    reset_settings_cache()

    url = get_database_url()

    assert "ep-apps.database.westus2.cloud.databricks.com" in url
    assert "sp-client-id%40apps" in url
    assert use_lakebase_oauth() is True


def test_generate_lakebase_credential_uses_rest_when_postgres_attr_missing(monkeypatch):
    class FakeApiClient:
        def do(self, method, path, body=None):
            assert method == "POST"
            assert path == "/api/2.0/postgres/credentials"
            assert body == {"endpoint": "projects/p/branches/b/endpoints/e"}
            return {"token": "oauth-token", "expire_time": "2026-06-29T12:00:00Z"}

    class FakeWorkspaceClient:
        api_client = FakeApiClient()

    monkeypatch.setattr(
        "shared.database.connection._get_workspace_client",
        lambda: FakeWorkspaceClient(),
    )

    token, expire_time = _generate_lakebase_database_credential("projects/p/branches/b/endpoints/e")

    assert token == "oauth-token"
    assert expire_time == "2026-06-29T12:00:00Z"


def test_generate_lakebase_credential_prefers_client_postgres(monkeypatch):
    class FakeCredential:
        token = "sdk-token"
        expire_time = None

    class FakePostgres:
        def generate_database_credential(self, endpoint):
            assert endpoint == "projects/p/branches/b/endpoints/e"
            return FakeCredential()

    class FakeWorkspaceClient:
        postgres = FakePostgres()

    monkeypatch.setattr(
        "shared.database.connection._get_workspace_client",
        lambda: FakeWorkspaceClient(),
    )

    token, expire_time = _generate_lakebase_database_credential("projects/p/branches/b/endpoints/e")

    assert token == "sdk-token"
    assert expire_time is None


def test_lakebase_privilege_error_detected():
    from shared.database.connection import _is_insufficient_privilege_error

    err = RuntimeError(
        "(psycopg2.errors.InsufficientPrivilege) permission denied for schema public"
    )
    assert _is_insufficient_privilege_error(err) is True


def test_lakebase_privilege_hint_mentions_bootstrap_script(monkeypatch):
    from shared.database.connection import _lakebase_privilege_setup_hint

    _set_lakebase_postgres_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_USER", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    reset_settings_cache()

    hint = _lakebase_privilege_setup_hint()

    assert "lakebase_bootstrap_grants.sql" in hint
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in hint
