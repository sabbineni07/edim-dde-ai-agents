import os
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("USE_LOCAL_DATA", "true")

from API.src.main import app
from API.src.routes.jobs import JobRunSummary
from shared.services.environment_connection_service import (
    reset_environment_connection_store_for_tests,
)
from shared.services.environment_dataset_service import reset_environment_dataset_store_for_tests
from shared.services.platform_environment_service import reset_platform_environment_store_for_tests


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()


def test_job_run_summary_coerces_date_field():
    summary = JobRunSummary(
        job_run_id="jr-001-001",
        cluster_id="run-001-001",
        job_run_date=date(2026, 6, 2),
    )
    assert summary.job_run_date == "2026-06-02"


@pytest.mark.asyncio
async def test_list_workspaces_rejects_dataset_from_other_environment():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        local_resp = await ac.get("/api/environments/local/datasets")
        assert local_resp.status_code == 200, local_resp.text
        local_ds_id = local_resp.json()[0]["id"]

        resp = await ac.get(
            "/api/workspaces",
            params={"environment_id": "dim_dev", "dataset_id": local_ds_id},
        )
        assert resp.status_code == 400
        assert "does not belong" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_job_runs():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/workspaces/1234567890123456/jobs/job-001/runs",
            params={"start_date": "2026-06-01", "end_date": "2026-06-03"},
        )
        assert resp.status_code == 200, resp.text
        runs = resp.json()
        assert isinstance(runs, list)
        assert len(runs) > 0
        assert runs[0]["cluster_id"].startswith("run-001-")
        assert runs[0]["job_run_id"].startswith("jr-")
        assert runs[0]["job_run_id"] != runs[0]["cluster_id"]
        assert runs[0].get("dbr_version") == "15.4.x-scala2.12"
        assert runs[0].get("status") == "SUCCEEDED"


@pytest.mark.asyncio
async def test_list_job_runs_includes_failed_and_canceled_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/workspaces/1234567890123456/jobs/job-001/runs",
            params={"start_date": "2026-06-01", "end_date": "2026-06-03"},
        )
        assert resp.status_code == 200, resp.text
        by_run_id = {row["job_run_id"]: row for row in resp.json()}
        assert by_run_id["jr-001-002"]["status"] == "FAILED"
        assert by_run_id["jr-001-004"]["status"] == "CANCELED"
        assert by_run_id["jr-001-001"]["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_list_job_runs_rejects_excessive_date_range():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/workspaces/1234567890123456/jobs/job-001/runs",
            params={"start_date": "2026-01-01", "end_date": "2026-06-03"},
        )
        assert resp.status_code == 400
        assert "must not exceed" in resp.json()["detail"]
