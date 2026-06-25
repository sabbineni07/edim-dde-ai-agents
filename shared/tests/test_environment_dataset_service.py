"""Tests for environment dataset service."""

import os
from uuid import UUID

os.environ["USE_POSTGRES"] = "false"

from shared.services.environment_dataset_service import (
    EnvironmentDatasetService,
    reset_environment_dataset_store_for_tests,
)
from shared.services.environment_service import resolve_metrics_table_fqn
from shared.services.platform_environment_service import (
    list_environments,
    reset_platform_environment_store_for_tests,
)


def setup_function():
    reset_platform_environment_store_for_tests()
    reset_environment_dataset_store_for_tests()
    list_environments()


def test_seed_creates_default_dataset():
    envs = list_environments()
    dev = next(e for e in envs if e.id == "dim_dev")
    assert dev.default_dataset_id
    svc = EnvironmentDatasetService()
    ds = svc.get_dataset(UUID(dev.default_dataset_id))
    assert ds is not None
    assert ds.source_type == "databricks_delta"
    assert ds.table_fqn == "dim_dev.dde_metrics.job_cluster_metrics"
    assert ds.is_default


def test_resolve_metrics_table_uses_default_dataset():
    table = resolve_metrics_table_fqn("dim_dev")
    assert table == "dim_dev.dde_metrics.job_cluster_metrics"


def test_create_dataset_and_set_default():
    svc = EnvironmentDatasetService()
    rec = svc.create_dataset(
        environment_id="dim_uat",
        name="Alt metrics",
        source_type="databricks_delta",
        schema_profile="job_cluster_metrics",
        table_fqn="dim_uat.dde_metrics.job_cluster_metrics_alt",
        set_default=False,
    )
    assert rec.table_fqn.endswith("_alt")
    default = svc.set_default(rec.id)
    assert default.is_default
