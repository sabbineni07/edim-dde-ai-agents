"""Tests for health check endpoint."""
import pytest
import sys
from pathlib import Path
from httpx import ASGITransport, AsyncClient

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from API.src.main import app
except ImportError as e:
    # If import fails, skip tests (for environments without full setup)
    pytest.skip(f"Could not import app: {e}", allow_module_level=True)


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_endpoint():
    """Test readiness endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health/ready")
        assert response.status_code in [200, 503]  # 503 if services not ready
        data = response.json()
        assert "status" in data

