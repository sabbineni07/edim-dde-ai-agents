"""Tests for request-scoped metrics collector context."""

from unittest.mock import MagicMock, patch

from shared.factories.data_collector_context import (
    get_active_collector,
    reset_metrics_collector,
    set_metrics_collector,
)


def test_get_active_collector_prefers_request_scope():
    scoped = MagicMock(name="scoped_collector")
    token = set_metrics_collector(scoped)
    try:
        assert get_active_collector() is scoped
    finally:
        reset_metrics_collector(token)


def test_get_active_collector_falls_back_to_factory():
    factory_collector = MagicMock(name="factory_collector")
    with patch(
        "shared.factories.data_collector_factory.get_data_collector",
        return_value=factory_collector,
    ):
        assert get_active_collector() is factory_collector
