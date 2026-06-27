"""Request-scoped metrics collector override (recommendations / agent tools)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Optional

_metrics_collector: ContextVar[Optional[Any]] = ContextVar("metrics_collector", default=None)


def set_metrics_collector(collector: Any) -> Token:
    return _metrics_collector.set(collector)


def reset_metrics_collector(token: Token) -> None:
    _metrics_collector.reset(token)


def get_metrics_collector() -> Optional[Any]:
    return _metrics_collector.get()


def get_active_collector():
    """Return request-scoped collector when set, else platform default from settings."""
    scoped = get_metrics_collector()
    if scoped is not None:
        return scoped
    from shared.factories.data_collector_factory import get_data_collector

    return get_data_collector()
