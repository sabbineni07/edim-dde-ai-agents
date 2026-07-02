"""Tests for agent prompt update endpoints."""

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

os.environ["USE_POSTGRES"] = "false"

try:
    from httpx import ASGITransport, AsyncClient

    from API.src.main import app
    from shared.services.agent_content_service import (
        get_agent_content,
        reset_agent_content_store_for_tests,
        seed_agent_content_if_empty,
    )
except ImportError as e:
    pytest.skip(f"Could not import: {e}", allow_module_level=True)

ADMIN_HEADERS = {"X-User-Name": "admin"}
AGENT_ID = "dbx_cluster_tuning_agent"


@pytest.fixture(autouse=True)
def _fresh_agent_content():
    reset_agent_content_store_for_tests()
    seed_agent_content_if_empty()
    yield
    reset_agent_content_store_for_tests()


@pytest.mark.asyncio
async def test_list_agents():
    """Test agents list endpoint returns registered agents."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agents/")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    ids = [a["agent_id"] for a in data["agents"]]
    assert ids == ["dbx_cluster_tuning_agent"]


@pytest.mark.asyncio
async def test_get_agent_content():
    """Agent content endpoint returns seeded prompts and skills."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/agents/{AGENT_ID}/content",
            headers=ADMIN_HEADERS,
        )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == AGENT_ID
    assert data["definition"]["display_name"] == "DBX Cluster Tuning Agent"
    assert len(data["prompts"]) >= 4
    assert len(data["skills"]) >= 4
    chains = {p["chain_name"] for p in data["prompts"]}
    assert "sizing" in chains
    assert "explanation" in chains
    assert data["can_edit"] is True
    sizing_system = next(
        p for p in data["prompts"] if p["chain_name"] == "sizing" and p["role"] == "system"
    )
    assert sizing_system.get("usage_summary")
    assert sizing_system.get("usage_detail")
    assert data.get("chain_usage", {}).get("sizing", {}).get("summary")


@pytest.mark.asyncio
async def test_admin_can_update_prompt():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bundle = get_agent_content(AGENT_ID)
        assert bundle is not None
        human = next(
            p for p in bundle.prompts if p["chain_name"] == "sizing" and p["role"] == "human"
        )
        updated_text = human["content"].replace("Output one JSON object", "Return one JSON object")
        resp = await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers=ADMIN_HEADERS,
            json={"content": updated_text},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == updated_text
    assert data["version"] == human["version"] + 1
    assert data["updated_by"] == "admin"


@pytest.mark.asyncio
async def test_non_admin_cannot_update_prompt():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers={"X-User-Name": "regular_user"},
            json={"content": "invalid {current_config}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_prompt_validation_error():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers=ADMIN_HEADERS,
            json={"content": "Missing placeholders"},
        )
    assert resp.status_code == 400
    assert "placeholders" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_can_update_skill():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bundle = get_agent_content(AGENT_ID)
        assert bundle is not None
        skill = next(s for s in bundle.skills if s["skill_key"] == "vm_family_rules")
        updated_text = skill["content"] + "\n\n<!-- test edit -->"
        resp = await client.put(
            f"/api/agents/{AGENT_ID}/skills/vm_family_rules",
            headers=ADMIN_HEADERS,
            json={"content": updated_text},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == updated_text
    assert data["version"] == skill["version"] + 1


@pytest.mark.asyncio
async def test_list_prompt_versions_after_update():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bundle = get_agent_content(AGENT_ID)
        human = next(
            p for p in bundle.prompts if p["chain_name"] == "sizing" and p["role"] == "human"
        )
        updated_text = human["content"].replace("Output one JSON object", "Return one JSON object")
        await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers=ADMIN_HEADERS,
            json={"content": updated_text},
        )
        resp = await client.get(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human/versions",
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["kind"] == "prompt"
    assert len(data["versions"]) == 2
    assert data["versions"][0]["is_active"] is True
    assert data["versions"][1]["is_active"] is False


@pytest.mark.asyncio
async def test_diff_prompt_versions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bundle = get_agent_content(AGENT_ID)
        human = next(
            p for p in bundle.prompts if p["chain_name"] == "sizing" and p["role"] == "human"
        )
        updated_text = human["content"].replace("Output one JSON object", "Return one JSON object")
        await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers=ADMIN_HEADERS,
            json={"content": updated_text},
        )
        resp = await client.get(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human/diff",
            params={"from_version": 1, "to_version": 2},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["from_version"] == 1
    assert data["to_version"] == 2
    assert data["has_changes"] is True
    assert "Return one JSON object" in data["diff"]


@pytest.mark.asyncio
async def test_admin_can_reset_content_to_seed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bundle = get_agent_content(AGENT_ID)
        human = next(
            p for p in bundle.prompts if p["chain_name"] == "sizing" and p["role"] == "human"
        )
        await client.put(
            f"/api/agents/{AGENT_ID}/prompts/sizing/human",
            headers=ADMIN_HEADERS,
            json={"content": human["content"] + "\n<!-- changed -->\n"},
        )
        resp = await client.post(
            f"/api/agents/{AGENT_ID}/content/reset",
            headers=ADMIN_HEADERS,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["prompts_reset"] >= 1
    active = next(
        p
        for p in data["content"]["prompts"]
        if p["chain_name"] == "sizing" and p["role"] == "human"
    )
    assert "<!-- changed -->" not in active["content"]


@pytest.mark.asyncio
async def test_non_admin_cannot_reset_content():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/agents/{AGENT_ID}/content/reset",
            headers={"X-User-Name": "regular_user"},
        )
    assert resp.status_code == 403
