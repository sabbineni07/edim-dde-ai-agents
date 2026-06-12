"""Tests for platform environments API and admin updates."""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["USE_POSTGRES"] = "false"

from API.src.main import app
from shared.services.environment_connection_service import (
    reset_environment_connection_store_for_tests,
)
from shared.services.platform_environment_service import reset_platform_environment_store_for_tests

_SAMPLE_CSV = Path(__file__).resolve().parents[2] / "data" / "sample_job_metrics.csv"


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()


@pytest.mark.asyncio
async def test_list_environments_from_store():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/environments", headers={"X-User-Name": "tester"})
        assert resp.status_code == 200
        envs = resp.json()
        ids = {e["id"] for e in envs}
        assert ids >= {"dim_dev", "dim_uat", "dim_intg", "dim_prod", "sdbx", "local"}
        dev = next(e for e in envs if e["id"] == "dim_dev")
        assert dev["metrics_connection_count"] >= 1
        assert dev.get("default_metrics_connection_id")


@pytest.mark.asyncio
async def test_admin_can_update_environment_metadata():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            "/api/environments/dim_dev",
            headers={"X-User-Name": "admin"},
            json={
                "display_name": "Dev updated",
                "sort_order": 5,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["display_name"] == "Dev updated"
        assert body["sort_order"] == 5


@pytest.mark.asyncio
async def test_admin_can_create_and_set_default_metrics_connection():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = {"X-User-Name": "admin"}
        resp = await ac.post(
            "/api/environments/dim_dev/connections",
            headers=headers,
            json={
                "name": "Dev WH",
                "connection_type": "databricks",
                "config": {
                    "databricks_server_hostname": "adb-test.azuredatabricks.net",
                    "databricks_http_path": "/sql/1.0/warehouses/test",
                    "databricks_job_cluster_metrics_table": "dim_dev.metrics.cluster_jobs",
                },
                "set_default": True,
            },
        )
        assert resp.status_code == 200, resp.text
        conn = resp.json()
        assert conn["is_default"] is True

        env_resp = await ac.get("/api/environments/dim_dev", headers=headers)
        assert env_resp.json()["readiness"] == "ready"


@pytest.mark.asyncio
async def test_non_admin_cannot_update_environment():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            "/api/environments/dim_dev",
            headers={"X-User-Name": "regular_user"},
            json={"display_name": "hacked"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_local_template_download():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/environments/local/template")
        assert resp.status_code == 200
        assert "workspace_id" in resp.text


@pytest.mark.asyncio
async def test_local_csv_upload_and_workspaces():
    content = _SAMPLE_CSV.read_bytes()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        headers = {"X-User-Name": "upload_user"}
        resp = await ac.post(
            "/api/environments/local/upload",
            headers=headers,
            files={"file": ("metrics.csv", content, "text/csv")},
        )
        assert resp.status_code == 200, resp.text

        resp = await ac.get("/api/workspaces", params={"environment_id": "local"}, headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
