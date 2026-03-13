"""Tests for agent discovery endpoints."""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from httpx import ASGITransport, AsyncClient

    from API.src.main import app
except ImportError as e:
    pytest.skip(f"Could not import: {e}", allow_module_level=True)


@pytest.mark.asyncio
async def test_list_agents():
    """Test agents list endpoint returns registered agents."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/agents/")
    assert response.status_code == 200
    data = response.json()
    assert "agent_ids" in data
    assert isinstance(data["agent_ids"], list)
    assert "cluster_config" in data["agent_ids"]
