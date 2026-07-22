"""Tests for browse inventory vs agent evidence dataset boundaries."""

import pytest

from shared.config.dataset_profiles import (
    BROWSE_SCHEMA_PROFILE,
    is_browse_schema_profile,
    list_schema_profiles,
    require_browse_schema_profile,
    validate_schema_profile,
)
from shared.services.environment_dataset_service import (
    EnvironmentDatasetService,
    reset_environment_dataset_store_for_tests,
)


@pytest.fixture(autouse=True)
def _mem_store(monkeypatch):
    monkeypatch.setenv("USE_POSTGRES", "false")
    reset_environment_dataset_store_for_tests()
    yield
    reset_environment_dataset_store_for_tests()


def test_job_inventory_profile_listed_as_browse_default():
    profiles = {p["schema_profile"]: p for p in list_schema_profiles()}
    assert BROWSE_SCHEMA_PROFILE in profiles
    assert profiles[BROWSE_SCHEMA_PROFILE]["is_browse_default"] is True
    assert profiles["job_cluster_metrics"]["is_browse_default"] is False


def test_require_browse_rejects_evidence_profiles():
    require_browse_schema_profile("job_inventory")
    with pytest.raises(ValueError, match="job_inventory"):
        require_browse_schema_profile("job_cluster_metrics")
    with pytest.raises(ValueError, match="job_inventory"):
        require_browse_schema_profile("spark_logs")


def test_set_default_only_allows_job_inventory():
    svc = EnvironmentDatasetService()
    inv = svc.create_dataset(
        environment_id="env1",
        name="Inventory",
        source_type="databricks_delta",
        schema_profile="job_inventory",
        table_fqn="cat.schema.job_inventory",
        set_default=False,
    )
    metrics = svc.create_dataset(
        environment_id="env1",
        name="Metrics",
        source_type="databricks_delta",
        schema_profile="job_cluster_metrics",
        table_fqn="cat.schema.job_cluster_metrics",
        set_default=False,
    )
    with pytest.raises(ValueError, match="job_inventory"):
        svc.set_default(metrics.id)
    updated = svc.set_default(inv.id)
    assert updated.is_default is True
    assert is_browse_schema_profile(updated.schema_profile)


def test_create_with_set_default_requires_inventory():
    svc = EnvironmentDatasetService()
    with pytest.raises(ValueError, match="job_inventory"):
        svc.create_dataset(
            environment_id="env1",
            name="Metrics",
            source_type="databricks_delta",
            schema_profile="job_cluster_metrics",
            table_fqn="cat.schema.job_cluster_metrics",
            set_default=True,
        )
    rec = svc.create_dataset(
        environment_id="env1",
        name="Inventory",
        source_type="databricks_delta",
        schema_profile="job_inventory",
        table_fqn="cat.schema.job_inventory",
        set_default=True,
    )
    assert rec.is_default is True


def test_get_default_dataset_ignores_non_inventory():
    svc = EnvironmentDatasetService()
    svc.create_dataset(
        environment_id="env1",
        name="Metrics",
        source_type="databricks_delta",
        schema_profile="job_cluster_metrics",
        table_fqn="cat.schema.job_cluster_metrics",
        set_default=False,
    )
    # Manually mark non-inventory as default in mem (legacy) — get_default should ignore
    from shared.services import environment_dataset_service as eds

    for row in eds._MEM_DATASETS.values():
        if row["schema_profile"] == "job_cluster_metrics":
            row["is_default"] = True
    assert svc.get_default_dataset("env1") is None

    inv = svc.create_dataset(
        environment_id="env1",
        name="Inventory",
        source_type="databricks_delta",
        schema_profile="job_inventory",
        table_fqn="cat.schema.job_inventory",
        set_default=True,
    )
    assert svc.get_default_dataset("env1").id == inv.id


def test_validate_job_inventory_profile():
    assert validate_schema_profile("job_inventory") == "job_inventory"
