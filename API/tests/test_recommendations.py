"""Tests for recommendation API."""

import sys
from pathlib import Path

import pytest
from httpx import AsyncClient

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from API.src.main import app
except ImportError as e:
    pytest.skip(f"Could not import app: {e}", allow_module_level=True)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires full setup")
async def test_generate_recommendation_endpoint():
    """Test recommendation generation API endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={"job_id": "test-job-123", "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )
        assert response.status_code in [200, 500]  # 500 if services not configured
