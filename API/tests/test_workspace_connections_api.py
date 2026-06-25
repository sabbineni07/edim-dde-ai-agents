"""Workspace agent API — bindings reference environment datasets and connections."""

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
from shared.services.workspace_agent_service import reset_workspace_agent_store_for_tests

WS = "1234567890123456"
ENV = "dim_dev"
ADMIN_HEADERS = {"X-User-Name": "admin"}


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()
    reset_workspace_agent_store_for_tests()


async def _create_env_connection(ac: AsyncClient, **kwargs) -> str:
    resp = await ac.post(
        f"/api/environments/{ENV}/connections",
        json=kwargs,
        headers=ADMIN_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _default_metrics_dataset_id(ac: AsyncClient) -> str:
    resp = await ac.get(f"/api/environments/{ENV}/datasets")
    assert resp.status_code == 200, resp.text
    datasets = resp.json()
    default = next(d for d in datasets if d["is_default"])
    return default["id"]


@pytest.mark.asyncio
async def test_workspace_agents_with_dataset_and_llm_bindings():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        metrics_ds_id = await _default_metrics_dataset_id(ac)
        llm_conn_id = await _create_env_connection(
            ac,
            connection_type="ai_foundry",
            name="Dev OpenAI",
            config={
                "azure_openai_endpoint": "https://my-openai.openai.azure.com/",
                "azure_openai_deployment_name": "gpt-4o",
            },
        )

        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "environment_id": ENV,
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Sizing default",
                "bindings": {"metrics": metrics_ds_id, "llm": llm_conn_id},
            },
        )
        assert resp.status_code == 200, resp.text
        wa_id = resp.json()["id"]

        resp = await ac.get("/api/agents/dbx_cluster_tuning_agent/connection-manifest")
        assert resp.status_code == 200
        manifest = resp.json()
        assert manifest["roles"]["metrics"]["kind"] == "dataset"
        assert "llm" in manifest["required_roles"]

        resp = await ac.get(f"/api/workspaces/{WS}/agents")
        assert resp.status_code == 200
        assert any(a["id"] == wa_id for a in resp.json())

        resp = await ac.delete(f"/api/workspaces/{WS}/agents/{wa_id}")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_same_dataset_can_bind_multiple_workspace_agents():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        metrics_ds_id = await _default_metrics_dataset_id(ac)
        llm_id = await _create_env_connection(
            ac,
            connection_type="ai_foundry",
            name="Shared LLM",
            config={
                "azure_openai_endpoint": "https://my-openai.openai.azure.com/",
                "azure_openai_deployment_name": "gpt-4o",
            },
        )

        bindings = {"metrics": metrics_ds_id, "llm": llm_id}
        for name in ("Agent 1", "Agent 2"):
            resp = await ac.post(
                f"/api/workspaces/{WS}/agents",
                json={
                    "environment_id": ENV,
                    "agent_id": "dbx_cluster_tuning_agent",
                    "name": name,
                    "bindings": bindings,
                },
            )
            assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_agent_rejects_dataset_from_wrong_environment():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/environments/local/datasets")
        assert resp.status_code == 200, resp.text
        local_ds_id = resp.json()[0]["id"]

        llm_id = await _create_env_connection(
            ac,
            connection_type="ai_foundry",
            name="Dev LLM",
            config={
                "azure_openai_endpoint": "https://my-openai.openai.azure.com/",
                "azure_openai_deployment_name": "gpt-4o",
            },
        )

        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "environment_id": ENV,
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Bad binding",
                "bindings": {"metrics": local_ds_id, "llm": llm_id},
            },
        )
        assert resp.status_code == 400, resp.text
        assert "does not belong to environment" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_agent_rejects_connection_used_as_metrics_when_dataset_expected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        metrics_conn_id = await _create_env_connection(
            ac,
            connection_type="local_dataset",
            name="Sample CSV",
            config={"local_data_path": "data/sample_job_metrics.csv"},
        )
        llm_id = await _create_env_connection(
            ac,
            connection_type="ai_foundry",
            name="Dev LLM",
            config={
                "azure_openai_endpoint": "https://my-openai.openai.azure.com/",
                "azure_openai_deployment_name": "gpt-4o",
            },
        )

        resp = await ac.post(
            f"/api/workspaces/{WS}/agents",
            json={
                "environment_id": ENV,
                "agent_id": "dbx_cluster_tuning_agent",
                "name": "Legacy binding",
                "bindings": {"metrics": metrics_conn_id, "llm": llm_id},
            },
        )
        assert resp.status_code == 400, resp.text
        assert "Dataset not found" in resp.json()["detail"]
