"""API tests for connection-scoped chat."""

import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_MOCK_LLM", "true")
os.environ.setdefault("USE_POSTGRES", "false")

from API.src.main import app  # noqa: E402
from shared.services.environment_connection_service import EnvironmentConnectionService


@pytest.fixture
def chat_connections(monkeypatch):
    monkeypatch.setenv("USE_POSTGRES", "false")
    from shared.services import environment_connection_service as ecs

    ecs._MEM_CONNECTIONS.clear()

    svc = EnvironmentConnectionService()
    llm = svc.create_connection(
        environment_id="dim_dev",
        name="Chat Foundry",
        connection_type="ai_foundry",
        purpose="llm",
        config={
            "azure_openai_endpoint": "https://test.services.ai.azure.com",
            "azure_openai_deployment_name": "gpt-4o",
        },
        validate=False,
    )
    return llm


@pytest.mark.asyncio
async def test_chat_requires_environment(chat_connections):
    llm = chat_connections
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/",
            json={
                "question": "What jobs are CPU heavy?",
                "environment_id": "missing_env",
                "llm_connection_id": str(llm.id),
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_mock_llm_no_rag(chat_connections, monkeypatch):
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    from shared.services import platform_environment_service as pes

    if not pes.get_environment("dim_dev"):
        monkeypatch.setattr(
            pes,
            "get_environment",
            lambda eid: {"id": eid} if eid == "dim_dev" else None,
        )

    llm = chat_connections
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/",
            json={
                "question": "Summarize cluster tuning guidance",
                "environment_id": "dim_dev",
                "llm_connection_id": str(llm.id),
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "answer" in body
    assert body["sources"] == []
    assert body["context_summary"]["mock_llm"] is True


@pytest.mark.asyncio
async def test_chat_invalid_connection_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/chat/",
            json={
                "question": "Hello",
                "environment_id": "dim_dev",
                "llm_connection_id": str(uuid4()),
            },
        )
    assert resp.status_code in (404, 400)
