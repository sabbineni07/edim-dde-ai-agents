"""Tests for Azure token credential selection on Databricks Apps."""


def test_client_secret_credential_from_databricks_app_env(monkeypatch):
    from shared.auth import azure_tokens

    azure_tokens._default_credential.cache_clear()

    monkeypatch.setenv("DATABRICKS_APP_NAME", "edim-dde-ai-agents-api")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "app-client-id")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "app-client-secret")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-id")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)

    kwargs = azure_tokens._client_secret_credential_kwargs()
    assert kwargs == {
        "tenant_id": "tenant-id",
        "client_id": "app-client-id",
        "client_secret": "app-client-secret",
    }

    azure_tokens._default_credential.cache_clear()
