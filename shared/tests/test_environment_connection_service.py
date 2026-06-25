"""Tests for environment connection service."""

import os

os.environ["USE_POSTGRES"] = "false"

from shared.services.environment_connection_service import (
    EnvironmentConnectionService,
    reset_environment_connection_store_for_tests,
)
from shared.services.environment_dataset_service import reset_environment_dataset_store_for_tests
from shared.services.platform_environment_service import (
    list_environments,
    reset_platform_environment_store_for_tests,
)


def setup_function():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()
    list_environments()


def test_seed_creates_default_metrics_connection():
    envs = list_environments()
    dev = next(e for e in envs if e.id == "dim_dev")
    assert dev.default_metrics_connection_id


def test_create_and_set_default():
    svc = EnvironmentConnectionService()
    rec = svc.create_connection(
        environment_id="dim_uat",
        name="UAT metrics",
        connection_type="databricks",
        purpose="metrics",
        config={
            "databricks_server_hostname": "adb.example.net",
            "databricks_http_path": "/sql/1.0/warehouses/x",
        },
        set_default=True,
    )
    assert rec.is_default
    default = svc.get_default_connection("dim_uat", "metrics")
    assert default is not None
    assert default.id == rec.id
