"""Tests for environment datasets API."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")

from API.src.main import app
from shared.services.environment_connection_service import (
    reset_environment_connection_store_for_tests,
)
from shared.services.environment_dataset_service import reset_environment_dataset_store_for_tests
from shared.services.platform_environment_service import reset_platform_environment_store_for_tests

ENV = "dim_dev"
ADMIN_HEADERS = {"X-User-Name": "admin"}


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()


@pytest.mark.asyncio
async def test_list_seeded_datasets():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(f"/api/environments/{ENV}/datasets")
        assert resp.status_code == 200, resp.text
        datasets = resp.json()
        assert len(datasets) >= 1
        default = next(d for d in datasets if d["is_default"])
        assert default["table_fqn"] == "dim_dev.dde_metrics.job_cluster_metrics"


@pytest.mark.asyncio
async def test_dataset_profiles_catalog():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/platform/dataset-profiles")
        assert resp.status_code == 200
        profiles = resp.json()["schema_profiles"]
        assert any(p["schema_profile"] == "job_cluster_metrics" for p in profiles)


@pytest.mark.asyncio
async def test_admin_create_update_delete_dataset():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/environments/{ENV}/datasets",
            headers=ADMIN_HEADERS,
            json={
                "name": "Extra table",
                "source_type": "databricks_delta",
                "schema_profile": "job_cluster_metrics",
                "table_fqn": "dim_dev.dde_metrics.extra_metrics",
            },
        )
        assert resp.status_code == 200, resp.text
        ds_id = resp.json()["id"]

        resp = await ac.put(
            f"/api/environments/{ENV}/datasets/{ds_id}",
            headers=ADMIN_HEADERS,
            json={"name": "Extra table renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Extra table renamed"

        resp = await ac.delete(f"/api/environments/{ENV}/datasets/{ds_id}", headers=ADMIN_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True


@pytest.mark.asyncio
async def test_environments_list_includes_dataset_count():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/environments", headers={"X-User-Name": "tester"})
        assert resp.status_code == 200
        dev = next(e for e in resp.json() if e["id"] == ENV)
        assert dev.get("default_dataset_id")
        assert dev.get("metrics_dataset_count", 0) >= 1
