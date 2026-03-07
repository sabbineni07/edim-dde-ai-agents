"""Tests for cluster config agent."""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from AI.src.agents.cluster_config_agent import ClusterConfigAgent
except ImportError as e:
    pytest.skip(f"Could not import ClusterConfigAgent: {e}", allow_module_level=True)


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires Azure OpenAI and Databricks")
async def test_generate_recommendation():
    """Test recommendation generation."""
    agent = ClusterConfigAgent()
    result = await agent.generate_recommendation(
        job_id="test-job-123",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    assert "recommendation" in result
    assert "explanation" in result

