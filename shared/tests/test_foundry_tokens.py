"""Tests for Foundry token resolution (service credential + Azure fallback)."""

from types import SimpleNamespace

import pytest

from shared.auth import foundry_tokens
from shared.auth.azure_tokens import AZURE_FOUNDRY_AAD_SCOPE
from shared.config.settings import Settings


@pytest.fixture(autouse=True)
def _clear_cached_token_env(monkeypatch):
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    monkeypatch.delenv("DATABRICKS_SERVICE_CREDENTIAL_NAME", raising=False)
    monkeypatch.delenv("DATABRICKS_DEFAULT_SERVICE_CREDENTIAL_NAME", raising=False)


def test_resolve_service_credential_name_from_settings():
    cfg = Settings(_env_file=None, databricks_service_credential_name="from-settings")
    assert foundry_tokens._resolve_service_credential_name(cfg) == "from-settings"


def test_resolve_service_credential_name_from_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_SERVICE_CREDENTIAL_NAME", "from-env")
    cfg = Settings(_env_file=None)
    assert foundry_tokens._resolve_service_credential_name(cfg) == "from-env"


def test_get_foundry_access_token_uses_explicit_token():
    cfg = Settings(_env_file=None, azure_openai_access_token="explicit-token")
    assert foundry_tokens.get_foundry_access_token(cfg) == "explicit-token"


def test_get_foundry_access_token_from_service_credential(monkeypatch):
    class FakeToken:
        token = "sc-foundry-token"

    class FakeProvider:
        def get_token(self, scope):
            assert scope == AZURE_FOUNDRY_AAD_SCOPE
            return FakeToken()

    cfg = Settings(_env_file=None, databricks_service_credential_name="my-sc")
    monkeypatch.setattr(
        foundry_tokens,
        "_get_databricks_service_credential_provider",
        lambda name: FakeProvider() if name == "my-sc" else None,
    )

    token = foundry_tokens.get_foundry_access_token(cfg)
    assert token == "sc-foundry-token"
    assert cfg.azure_openai_access_token == "sc-foundry-token"


def test_get_foundry_access_token_skips_service_credential_on_apps(monkeypatch):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "edim-dde-ai-agents-api")
    cfg = Settings(_env_file=None, databricks_service_credential_name="my-sc")

    called = {"provider": False}

    def _should_not_call(_name):
        called["provider"] = True
        raise AssertionError("service credential must be skipped on Apps")

    monkeypatch.setattr(
        foundry_tokens,
        "_get_databricks_service_credential_provider",
        _should_not_call,
    )
    monkeypatch.setattr(
        foundry_tokens,
        "get_azure_access_token",
        lambda scope: "azure-identity-token",
    )

    token = foundry_tokens.get_foundry_access_token(cfg)
    assert token == "azure-identity-token"
    assert called["provider"] is False
    assert cfg.azure_openai_access_token == "azure-identity-token"


def test_get_foundry_access_token_falls_back_when_provider_missing(monkeypatch):
    cfg = Settings(_env_file=None, databricks_service_credential_name="missing-sc")
    monkeypatch.setattr(
        foundry_tokens,
        "_get_databricks_service_credential_provider",
        lambda _name: None,
    )
    monkeypatch.setattr(
        foundry_tokens,
        "get_azure_access_token",
        lambda scope: f"azure:{scope}",
    )

    token = foundry_tokens.get_foundry_access_token(cfg)
    assert token == f"azure:{AZURE_FOUNDRY_AAD_SCOPE}"


def test_get_foundry_access_token_falls_back_when_provider_raises(monkeypatch):
    class BoomProvider:
        def get_token(self, _scope):
            raise RuntimeError("credential denied")

    cfg = Settings(_env_file=None, databricks_service_credential_name="bad-sc")
    monkeypatch.setattr(
        foundry_tokens,
        "_get_databricks_service_credential_provider",
        lambda _name: BoomProvider(),
    )
    monkeypatch.setattr(
        foundry_tokens,
        "get_azure_access_token",
        lambda _scope: "azure-fallback",
    )

    assert foundry_tokens.get_foundry_access_token(cfg) == "azure-fallback"


def test_foundry_token_provider_callable(monkeypatch):
    cfg = Settings(_env_file=None, azure_openai_access_token="cached")
    provider = foundry_tokens.foundry_token_provider(cfg)
    assert provider() == "cached"


def test_resolve_dbutils_from_builtins(monkeypatch):
    fake = SimpleNamespace(credentials=SimpleNamespace())
    monkeypatch.setattr(foundry_tokens.builtins, "dbutils", fake, raising=False)
    assert foundry_tokens._resolve_dbutils() is fake
