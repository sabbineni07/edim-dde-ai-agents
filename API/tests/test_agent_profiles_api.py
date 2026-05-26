import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")

from API.src.main import app


@pytest.mark.asyncio
async def test_agent_profiles_crud_in_memory():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # create
        resp = await ac.post(
            "/api/agent-profiles/",
            json={
                "agent_id": "job_run_cluster_sizing",
                "name": "Fast",
                "overrides": {"rag": {"backend": "none"}},
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        pid = body["id"]
        assert body["agent_id"] == "job_run_cluster_sizing"
        assert body["overrides"]["vector_retrieval_backend"] == "none"

        # list
        resp = await ac.get("/api/agent-profiles/?agent_id=job_run_cluster_sizing")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json())

        # update
        resp = await ac.put(
            f"/api/agent-profiles/{pid}",
            json={"overrides": {"sizing": {"cost_retry_enabled": True}}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["overrides"]["recommendation_cost_retry_enabled"] is True

        # delete
        resp = await ac.delete(f"/api/agent-profiles/{pid}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
