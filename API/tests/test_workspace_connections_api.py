import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")

from API.src.main import app

WS = "1234567890123456"


@pytest.mark.asyncio
async def test_workspace_connections_and_agents_crud():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # connection types catalog
        resp = await ac.get("/api/platform/connection-types")
        assert resp.status_code == 200
        payload = resp.json()["connection_types"]
        types = {t["connection_type"] for t in payload}
        assert "databricks" in types
        dbx = next(t for t in payload if t["connection_type"] == "databricks")
        field_keys = {f["key"] for f in dbx["fields"]}
        assert "credential_env_prefix" not in field_keys
        assert dbx.get("auth_note")
        assert "credential_hints" not in dbx

        # create local_dataset connection
        resp = await ac.post(
            f"/api/workspaces/{WS}/connections",
            json={
                "connection_type": "local_dataset",
                "name": "Sample CSV",
                "config": {"local_data_path": "data/sample_job_metrics.csv"},
            },
        )
        assert resp.status_code == 200, resp.text
        metrics_conn_id = resp.json()["id"]

        # create workspace agent
        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Sizing default",
                "bindings": {"metrics": metrics_conn_id},
            },
        )
        assert resp.status_code == 200, resp.text
        wa_id = resp.json()["id"]

        # manifest endpoint
        resp = await ac.get("/api/agents/dbx_cluster_tuning_agent/connection-manifest")
        assert resp.status_code == 200
        assert "metrics" in resp.json()["roles"]

        # list
        resp = await ac.get(f"/api/workspaces/{WS}/agents")
        assert resp.status_code == 200
        assert any(a["id"] == wa_id for a in resp.json())

        # delete agent then connection
        resp = await ac.delete(f"/api/workspaces/{WS}/agents/{wa_id}")
        assert resp.status_code == 200
        resp = await ac.delete(f"/api/workspaces/{WS}/connections/{metrics_conn_id}")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_databricks_connection_exclusive_per_workspace_agent():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            f"/api/workspaces/{WS}/connections",
            json={
                "connection_type": "databricks",
                "name": "DBX A",
                "config": {
                    "databricks_server_hostname": "adb-1.azuredatabricks.net",
                    "databricks_http_path": "/sql/1.0/warehouses/abc",
                    "databricks_job_cluster_metrics_table": "catalog.schema.metrics",
                },
            },
        )
        assert resp.status_code == 200, resp.text
        dbx_id = resp.json()["id"]

        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Agent 1",
                "bindings": {"metrics": dbx_id},
            },
        )
        assert resp.status_code == 200, resp.text
        wa1 = resp.json()["id"]

        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Agent 2",
                "bindings": {"metrics": dbx_id},
            },
        )
        assert resp.status_code == 409, resp.text

        await ac.delete(f"/api/workspaces/{WS}/agents/{wa1}")
        await ac.delete(f"/api/workspaces/{WS}/connections/{dbx_id}")
