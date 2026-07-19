"""Tests for environment readiness and metrics table resolution."""

import os
from uuid import UUID

os.environ["USE_POSTGRES"] = "false"

from shared.services.environment_connection_service import (
    EnvironmentConnectionService,
    reset_environment_connection_store_for_tests,
)
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
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()
    list_environments()


def test_resolve_metrics_table_from_seeded_evidence_dataset():
    svc = EnvironmentDatasetService()
    rows = svc.list_datasets(environment_id="dim_dev")
    metrics = next(r for r in rows if r.schema_profile == "job_cluster_metrics")
    table = resolve_metrics_table_fqn("dim_dev", dataset_id=str(metrics.id), for_browse=False)
    assert table == "dim_dev.dde_metrics.job_cluster_metrics"


def test_resolve_browse_table_requires_inventory_default():
    import pytest

    with pytest.raises(ValueError, match="job_inventory"):
        resolve_metrics_table_fqn("dim_dev", for_browse=True)


def test_resolve_metrics_table_legacy_connection_fallback():
    table = resolve_metrics_table_fqn(
        "unknown_env",
        {"databricks_job_cluster_metrics_table": "legacy.catalog.table"},
    )
    assert table == "legacy.catalog.table"


def test_seeded_connection_has_no_table_in_config():
    envs = list_environments()
    dev = next(e for e in envs if e.id == "dim_dev")
    assert dev.default_metrics_connection_id
    svc = EnvironmentConnectionService()
    conn = svc.get_connection(UUID(dev.default_metrics_connection_id))
    assert conn is not None
    assert "databricks_job_cluster_metrics_table" not in conn.config


def test_wh_only_connection_create():
    svc = EnvironmentConnectionService()
    rec = svc.create_connection(
        environment_id="dim_uat",
        name="UAT WH",
        connection_type="databricks",
        purpose="metrics",
        config={
            "databricks_server_hostname": "adb.example.net",
            "databricks_http_path": "/sql/1.0/warehouses/x",
        },
    )
    assert "databricks_job_cluster_metrics_table" not in rec.config
