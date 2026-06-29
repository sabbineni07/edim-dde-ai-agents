"""Tests for database error handling when Postgres is required."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shared.config.loader import reset_settings_cache
from shared.database.availability import (
    handle_database_error,
    postgres_required,
    require_database_import,
)
from shared.services.observability_service import ObservabilityService


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def configure_use_postgres(monkeypatch):
    def _configure(enabled: bool):
        from shared.config import loader

        stub = SimpleNamespace(use_postgres=enabled)
        monkeypatch.setattr(loader, "get_agent_settings", lambda *_a, **_k: stub)
        reset_settings_cache()

    return _configure


def test_postgres_required_reflects_use_postgres(configure_use_postgres):
    configure_use_postgres(True)
    assert postgres_required() is True

    configure_use_postgres(False)
    assert postgres_required() is False


def test_require_database_import_raises_when_postgres_enabled(configure_use_postgres):
    configure_use_postgres(True)
    with pytest.raises(RuntimeError, match="database modules are unavailable"):
        require_database_import(False)


def test_require_database_import_noop_when_postgres_disabled(configure_use_postgres):
    configure_use_postgres(False)
    require_database_import(False)


def test_handle_database_error_reraises_when_postgres_enabled(configure_use_postgres):
    configure_use_postgres(True)
    exc = RuntimeError("connection failed")
    with pytest.raises(RuntimeError, match="connection failed"):
        handle_database_error("test_event", exc)


def test_handle_database_error_logs_only_when_postgres_disabled(configure_use_postgres):
    configure_use_postgres(False)
    exc = RuntimeError("connection failed")
    handle_database_error("test_event", exc)


def test_get_daily_summary_raises_when_postgres_enabled_and_db_fails(monkeypatch):
    monkeypatch.setattr("shared.database.availability.postgres_required", lambda: True)

    service = ObservabilityService()
    with patch(
        "shared.services.observability_service.get_database_session",
        side_effect=RuntimeError("No module named 'psycopg'"),
    ):
        with pytest.raises(RuntimeError, match="No module named 'psycopg'"):
            service.get_daily_summary(date.today())


def test_get_daily_summary_returns_none_when_postgres_disabled_and_db_fails(monkeypatch):
    monkeypatch.setattr("shared.database.availability.postgres_required", lambda: False)

    service = ObservabilityService()
    with patch(
        "shared.services.observability_service.get_database_session",
        side_effect=RuntimeError("connection refused"),
    ):
        assert service.get_daily_summary(date.today()) is None


def test_get_daily_summary_returns_none_when_no_row(monkeypatch):
    monkeypatch.setattr("shared.database.availability.postgres_required", lambda: True)

    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None

    service = ObservabilityService()
    with patch(
        "shared.services.observability_service.get_database_session",
        return_value=session,
    ):
        assert service.get_daily_summary(date.today()) is None
