"""Tests for RAG integration in chains and services."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from AI.src.chains.cost_optimization_chain import CostOptimizationChain
    from AI.src.chains.pattern_analysis_chain import PatternAnalysisChain
    from AI.src.services.azure_search_service import AzureSearchService
    from AI.src.services.mock_llm_service import MockLLMService
    from shared.models.job_cluster_metrics import JobClusterMetrics
except ImportError as e:
    # If import fails, skip tests (for environments without full setup)
    pytest.skip(f"Could not import required modules: {e}", allow_module_level=True)


def _make_mock_openai_with_real_llm():
    """Create a mock AzureOpenAIService that returns a real Runnable (MockChatModel)."""
    mock_instance = MagicMock()
    mock_instance.get_llm.return_value = MockLLMService().get_llm()
    return mock_instance


class TestAzureSearchService:
    """Tests for AzureSearchService."""

    def test_initialization_without_config(self):
        """Test graceful degradation when Azure AI Search is not configured."""
        with patch("AI.src.services.azure_search_service.settings") as mock_settings:
            mock_settings.azure_search_endpoint = None
            mock_settings.azure_search_api_key = None

            service = AzureSearchService()
            assert service.client is None
            assert service.openai_service is None

    def test_index_recommendation_without_client(self):
        """Test index_recommendation returns False when client is None."""
        service = AzureSearchService()
        service.client = None

        result = service.index_recommendation(
            {
                "recommendation_id": "test-123",
                "rationale": "Test rationale",
                "detailed_explanation": "Test explanation",
            }
        )

        assert result is False

    def test_search_similar_without_client(self):
        """Test search_similar returns empty list when client is None."""
        service = AzureSearchService()
        service.client = None

        result = service.search_similar("test query", top_k=5)

        assert result == []

    def test_update_recommendation_quality_validation(self):
        """Test update_recommendation_quality validates quality values."""
        service = AzureSearchService()
        service.client = None

        # Invalid quality should return False
        result = service.update_recommendation_quality(
            recommendation_id="test-123", config_quality="invalid"
        )
        assert result is False

        # Valid quality should attempt update (but fail gracefully if no client)
        result = service.update_recommendation_quality(
            recommendation_id="test-123", config_quality="optimal"
        )
        assert result is False  # Because client is None, but validation passed


class TestPatternAnalysisChain:
    """Tests for PatternAnalysisChain with RAG."""

    def test_initialization_with_rag(self):
        """Test chain initializes with RAG enabled."""
        with patch(
            "AI.src.chains.pattern_analysis_chain.AzureOpenAIService",
            return_value=_make_mock_openai_with_real_llm(),
        ):
            chain = PatternAnalysisChain(use_rag=True)
            assert chain.use_rag is True

    def test_initialization_without_rag(self):
        """Test chain initializes with RAG disabled."""
        with patch(
            "AI.src.chains.pattern_analysis_chain.AzureOpenAIService",
            return_value=_make_mock_openai_with_real_llm(),
        ):
            chain = PatternAnalysisChain(use_rag=False)
            assert chain.use_rag is False

    @patch("AI.src.chains.pattern_analysis_chain.AzureOpenAIService")
    def test_analyze_without_rag(self, mock_openai):
        """Test analyze works without RAG."""
        mock_openai.return_value = _make_mock_openai_with_real_llm()
        chain = PatternAnalysisChain(use_rag=False)
        chain.chain = Mock()
        chain.chain.invoke = Mock(return_value="Test analysis")

        result = chain.analyze({"job_id": "test-123"})

        assert result == "Test analysis"
        chain.chain.invoke.assert_called_once()


class TestCostOptimizationChain:
    """Tests for CostOptimizationChain with RAG."""

    def test_initialization_with_rag(self):
        """Test chain initializes with RAG enabled."""
        with patch(
            "AI.src.chains.cost_optimization_chain.AzureOpenAIService",
            return_value=_make_mock_openai_with_real_llm(),
        ):
            chain = CostOptimizationChain(use_rag=True)
            assert chain.use_rag is True

    def test_initialization_without_rag(self):
        """Test chain initializes with RAG disabled."""
        with patch(
            "AI.src.chains.cost_optimization_chain.AzureOpenAIService",
            return_value=_make_mock_openai_with_real_llm(),
        ):
            chain = CostOptimizationChain(use_rag=False)
            assert chain.use_rag is False

    @patch("AI.src.chains.cost_optimization_chain.AzureOpenAIService")
    def test_optimize_without_rag(self, mock_openai):
        """Test optimize works without RAG."""
        import json

        mock_openai.return_value = _make_mock_openai_with_real_llm()
        chain = CostOptimizationChain(use_rag=False)
        chain.chain = Mock()
        chain.chain.invoke = Mock(
            return_value=json.dumps(
                {
                    "node_family": "E",
                    "vcpus": 8,
                    "min_workers": 1,
                    "max_workers": 8,
                    "auto_termination_minutes": None,
                    "rationale": "Test rationale",
                }
            )
        )

        result = chain.optimize(
            current_config={},
            job_cluster_metrics={},
            budget_constraints={},
            pattern_analysis="Test analysis",
        )

        assert result["node_family"] == "E"
        assert result["vcpus"] == 8
        chain.chain.invoke.assert_called_once()
