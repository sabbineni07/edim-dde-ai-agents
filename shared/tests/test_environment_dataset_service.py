"""Tests for environment dataset service."""

import os
from uuid import UUID

os.environ["USE_POSTGRES"] = "false"

import pytest

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


def test_seed_creates_evidence_dataset_not_browse_default():
    envs = list_environments()
    dev = next(e for e in envs if e.id == "dim_dev")
    # Browse default is not auto-seeded; register job_inventory in the UI.
    assert not dev.default_dataset_id
    svc = EnvironmentDatasetService()
    rows = svc.list_datasets(environment_id="dim_dev")
    assert rows
    metrics = next(r for r in rows if r.schema_profile == "job_cluster_metrics")
    assert metrics.table_fqn == "dim_dev.dde_metrics.job_cluster_metrics"
    assert metrics.is_default is False


def test_resolve_metrics_table_uses_explicit_evidence_dataset():
    svc = EnvironmentDatasetService()
    rows = svc.list_datasets(environment_id="dim_dev")
    metrics = next(r for r in rows if r.schema_profile == "job_cluster_metrics")
    table = resolve_metrics_table_fqn("dim_dev", dataset_id=str(metrics.id), for_browse=False)
    assert table == "dim_dev.dde_metrics.job_cluster_metrics"


def test_browse_default_requires_job_inventory():
    svc = EnvironmentDatasetService()
    with pytest.raises(ValueError, match="job_inventory"):
        svc.create_dataset(
            environment_id="dim_uat",
            name="Alt metrics",
            source_type="databricks_delta",
            schema_profile="job_cluster_metrics",
            table_fqn="dim_uat.dde_metrics.job_cluster_metrics_alt",
            set_default=True,
        )
    inv = svc.create_dataset(
        environment_id="dim_uat",
        name="Job inventory",
        source_type="databricks_delta",
        schema_profile="job_inventory",
        table_fqn="dim_uat.dde_metrics.job_inventory",
        set_default=True,
    )
    assert inv.is_default
    table = resolve_metrics_table_fqn("dim_uat", for_browse=True)
    assert table == "dim_uat.dde_metrics.job_inventory"
