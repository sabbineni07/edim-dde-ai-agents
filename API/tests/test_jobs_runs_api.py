import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("USE_LOCAL_DATA", "true")

from API.src.main import app


@pytest.mark.asyncio
async def test_list_job_runs():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/workspaces/1234567890123456/jobs/job-001/runs",
            params={"start_date": "2024-01-15", "end_date": "2024-01-20"},
        )
        assert resp.status_code == 200, resp.text
        runs = resp.json()
        assert isinstance(runs, list)
        assert len(runs) > 0
        assert runs[0]["job_run_id"].startswith("run-001-")
