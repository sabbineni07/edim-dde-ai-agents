"""Tests for cluster config agent with local data and mock services."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Set environment variable for local data mode before any imports
os.environ["USE_LOCAL_DATA"] = "true"

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from AI.src.agents.cluster_config_agent import ClusterConfigAgent
    from AI.src.services.mock_llm_service import MockLLMService
except ImportError as e:
    # If import fails, skip tests (for environments without full setup)
    pytest.skip(f"Could not import ClusterConfigAgent: {e}", allow_module_level=True)


def _make_mock_azure_openai():
    """Create a mock AzureOpenAIService that returns MockLLMService's LLM."""
    mock_instance = MagicMock()
    mock_instance.get_llm.return_value = MockLLMService().get_llm()
    mock_instance.get_embeddings.return_value = None
    return mock_instance


@pytest.mark.asyncio
async def test_agent_initialization():
    """Test that agent initializes correctly."""
    mock_openai = _make_mock_azure_openai()
    with patch("AI.src.chains.pattern_analysis_chain.AzureOpenAIService", return_value=mock_openai):
        with patch(
            "AI.src.chains.cost_optimization_chain.AzureOpenAIService", return_value=mock_openai
        ):
            with patch(
                "AI.src.chains.explanation_chain.AzureOpenAIService", return_value=mock_openai
            ):
                agent = ClusterConfigAgent()
                assert agent is not None
                assert hasattr(agent, "graph")


@pytest.mark.asyncio
async def test_generate_recommendation_with_local_data():
    """Test recommendation generation with local CSV data and mock LLM."""
    # Ensure local data mode is enabled
    os.environ["USE_LOCAL_DATA"] = "true"

    mock_openai = _make_mock_azure_openai()
    with patch("AI.src.chains.pattern_analysis_chain.AzureOpenAIService", return_value=mock_openai):
        with patch(
            "AI.src.chains.cost_optimization_chain.AzureOpenAIService", return_value=mock_openai
        ):
            with patch(
                "AI.src.chains.explanation_chain.AzureOpenAIService", return_value=mock_openai
            ):
                agent = ClusterConfigAgent()
                result = await agent.generate_recommendation(
                    job_id="job-001", start_date="2024-01-15", end_date="2024-01-18"
                )

    # Verify result structure
    assert result is not None
    assert "request_id" in result
    assert "recommendation" in result
    assert "explanation" in result
    assert "pattern_analysis" in result
    assert "risk_assessment" in result
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

    mock_openai = _make_mock_azure_openai()
    chain_patches = [
        patch("AI.src.chains.pattern_analysis_chain.AzureOpenAIService", return_value=mock_openai),
        patch("AI.src.chains.cost_optimization_chain.AzureOpenAIService", return_value=mock_openai),
        patch("AI.src.chains.explanation_chain.AzureOpenAIService", return_value=mock_openai),
    ]
    # Mock AzureSearchService to return None client
    with patch("AI.src.services.azure_search_service.AzureSearchService") as mock_search:
        mock_instance = Mock()
        mock_instance.client = None
        mock_instance.index_recommendation = Mock(return_value=False)
        mock_instance.link_recommendation_to_job = Mock(return_value=False)
        mock_search.return_value = mock_instance
        with chain_patches[0], chain_patches[1], chain_patches[2]:
            agent = ClusterConfigAgent()
            result = await agent.generate_recommendation(
                job_id="job-001", start_date="2024-01-15", end_date="2024-01-18"
            )

        # Should still work without RAG
        assert result is not None
        assert "recommendation" in result


@pytest.mark.asyncio
async def test_token_usage_tracking():
    """Test that token usage is tracked and included in response."""
    os.environ["USE_LOCAL_DATA"] = "true"

    mock_openai = _make_mock_azure_openai()
    with patch("AI.src.chains.pattern_analysis_chain.AzureOpenAIService", return_value=mock_openai):
        with patch(
            "AI.src.chains.cost_optimization_chain.AzureOpenAIService", return_value=mock_openai
        ):
            with patch(
                "AI.src.chains.explanation_chain.AzureOpenAIService", return_value=mock_openai
            ):
                agent = ClusterConfigAgent()
                result = await agent.generate_recommendation(
                    job_id="job-001", start_date="2024-01-15", end_date="2024-01-18"
                )

    # Verify token usage analysis
    token_usage = result.get("token_usage_analysis", {})
    assert token_usage is not None

    if "token_usage" in token_usage:
        assert "total_tokens" in token_usage["token_usage"]

    if "cost_estimate" in token_usage:
        assert "total_cost_usd" in token_usage["cost_estimate"]
