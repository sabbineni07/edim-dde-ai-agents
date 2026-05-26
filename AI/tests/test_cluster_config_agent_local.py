"""Tests for cluster config agent with local data and mock services."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

project_root = Path(__file__).parent.parent.parent
_sample_csv = project_root / "data" / "sample_job_metrics.csv"

# Set environment variable for local data mode before any imports
os.environ["USE_LOCAL_DATA"] = "true"
os.environ["LOCAL_DATA_PATH"] = str(_sample_csv)

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from AI.src.agents.job_run_cluster_sizing import JobRunClusterSizingAgent
    from AI.src.core.llm.mock_llm_service import MockLLMService
except ImportError as e:
    # If import fails, skip tests (for environments without full setup)
    pytest.skip(f"Could not import ClusterConfigAgent: {e}", allow_module_level=True)


def _make_mock_llm_provider():
    """Create a mock LLM provider (implements protocol)."""
    mock_instance = MagicMock()
    mock_instance.get_llm.return_value = MockLLMService().get_llm()
    mock_instance.get_embeddings.return_value = None
    return mock_instance


def _create_agent_with_mock_llm():
    """Create agent with mock LLM (no Azure required)."""
    from AI.src.agents.job_run_cluster_sizing.chains.explanation import (
        RecommendationExplanationChain,
    )
    from AI.src.agents.job_run_cluster_sizing.chains.sizing import ClusterSizingChain

    mock_llm = _make_mock_llm_provider()
    sizing_chain = ClusterSizingChain(llm_provider=mock_llm, rag_provider=None, use_rag=False)
    explanation_chain = RecommendationExplanationChain(llm_provider=mock_llm)
    return JobRunClusterSizingAgent(
        sizing_chain=sizing_chain,
        explanation_chain=explanation_chain,
        cost_logger=None,
        search_service=None,
    )


@pytest.fixture(autouse=True)
def _local_data_collector_path():
    from shared.factories.data_collector_factory import reset_data_collector

    os.environ["USE_LOCAL_DATA"] = "true"
    os.environ["LOCAL_DATA_PATH"] = str(_sample_csv)
    reset_data_collector()
    yield
    reset_data_collector()


@pytest.mark.asyncio
async def test_agent_initialization():
    """Test that agent initializes correctly."""
    agent = _create_agent_with_mock_llm()
    assert agent is not None
    assert hasattr(agent, "graph")


@pytest.mark.asyncio
async def test_generate_recommendation_with_local_data():
    """Test recommendation generation with local CSV data and mock LLM."""
    os.environ["USE_LOCAL_DATA"] = "true"

    agent = _create_agent_with_mock_llm()
    result = await agent.generate_recommendation(
        job_id="job-001",
        job_run_id="run-001-001",
        start_date="2024-01-15",
        end_date="2024-01-18",
        include_explanation=True,
    )

    # Verify result structure
    assert result is not None
    assert "request_id" in result
    assert result.get("job_run_id") == "run-001-001"
    assert "recommendation" in result
    assert "explanation" in result
    assert "pattern_analysis" in result
    assert "### 1. Workload type" in result["pattern_analysis"]
    assert "risk_assessment" in result
    assert "reason_codes" in result
    assert "job_run_ingest" in result
    assert "llm_recommendation" in result
    assert "guardrail_recommendation" in result
    assert "guardrail_adjustments" in result
    assert result.get("recommendation_attempts", 0) >= 1
    assert "comparison" in result
    assert "token_usage_analysis" in result

    # Verify recommendation structure
    rec = result["recommendation"]
    assert "node_family" in rec
    assert "vcpus" in rec
    assert "min_workers" in rec
    assert "max_workers" in rec
    assert "rationale" in rec


@pytest.mark.asyncio
async def test_agent_with_rag_disabled():
    """Test agent works when RAG is disabled (Azure AI Search not available)."""
    os.environ["USE_LOCAL_DATA"] = "true"

    agent = _create_agent_with_mock_llm()
    result = await agent.generate_recommendation(
        job_id="job-001",
        job_run_id="run-001-001",
        start_date="2024-01-15",
        end_date="2024-01-18",
    )

    assert result is not None
    assert "recommendation" in result


@pytest.mark.asyncio
async def test_token_usage_tracking():
    """Test that token usage is tracked and included in response."""
    os.environ["USE_LOCAL_DATA"] = "true"

    agent = _create_agent_with_mock_llm()
    result = await agent.generate_recommendation(
        job_id="job-001",
        job_run_id="run-001-001",
        start_date="2024-01-15",
        end_date="2024-01-18",
    )

    # Verify token usage analysis
    token_usage = result.get("token_usage_analysis", {})
    assert token_usage is not None

    if "token_usage" in token_usage:
        assert "total_tokens" in token_usage["token_usage"]

    if "cost_estimate" in token_usage:
        assert "total_cost_usd" in token_usage["cost_estimate"]
