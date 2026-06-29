"""Helpers for failing loudly when Postgres is required but unavailable."""

from __future__ import annotations

from shared.utils.logging import get_logger

logger = get_logger(__name__)


def postgres_required() -> bool:
    from shared.config.settings import settings

    return bool(getattr(settings, "use_postgres", False))


def require_database_import(database_available: bool) -> None:
    """Raise when USE_POSTGRES=true but database modules failed to import."""
    if postgres_required() and not database_available:
        raise RuntimeError("USE_POSTGRES is enabled but database modules are unavailable")


def handle_database_error(event: str, exc: Exception) -> None:
    """Log a database error and re-raise when Postgres is required."""
    logger.error(event, error=str(exc))
    if postgres_required():
        raise exc
