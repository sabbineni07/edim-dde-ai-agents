"""Tests for platform environment service."""

import os

os.environ["USE_POSTGRES"] = "false"

from shared.services.environment_connection_service import (
    reset_environment_connection_store_for_tests,
)
from shared.services.platform_environment_service import (
    get_environment,
    list_environments,
    reset_platform_environment_store_for_tests,
    update_environment,
)


def test_seed_and_table_fqn():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    envs = list_environments()
    assert any(e.id == "dim_dev" for e in envs)
    dev = get_environment("dim_dev")
    assert dev is not None
    assert dev.table_fqn == "dim_dev.dde_metrics.job_cluster_metrics"


def test_update_environment_in_memory():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    updated = update_environment(
        "dim_uat",
        {
            "display_name": "UAT updated",
            "sort_order": 25,
        },
    )
    assert updated.display_name == "UAT updated"
    assert updated.sort_order == 25
