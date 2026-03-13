"""FastAPI dependency injection - provides services for routes."""

from typing import Optional

from AI.src.agents import cluster_config  # noqa: F401 - ensures agents registered
from AI.src.agents.registry import create_agent, get_registered_agent_ids
from AI.src.chains.cost_optimization_chain import CostOptimizationChain
from AI.src.chains.explanation_chain import ExplanationChain
from AI.src.chains.pattern_analysis_chain import PatternAnalysisChain
from AI.src.services.azure_openai_service import AzureOpenAIService
from AI.src.services.azure_search_service import AzureSearchService
from shared.config.settings import settings
from shared.services.observability_service import ObservabilityService
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Singletons - created at first request, reused
_llm_provider: Optional[AzureOpenAIService] = None
_search_service: Optional[AzureSearchService] = None
_cost_logger: Optional[ObservabilityService] = None
_cluster_config_agent = None


def get_llm_provider() -> AzureOpenAIService:
    """Get LLM provider (Azure OpenAI). Cached singleton."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = AzureOpenAIService()
    return _llm_provider


def get_search_service() -> Optional[AzureSearchService]:
    """Get search service if configured. Cached singleton."""
    global _search_service
    if _search_service is None:
        try:
            svc = AzureSearchService()
            _search_service = svc if svc.client is not None else None
        except Exception as e:
            logger.warning("search_service_unavailable", error=str(e))
            _search_service = None
    return _search_service


def get_cost_logger() -> ObservabilityService:
    """Get cost logging service. Cached singleton."""
    global _cost_logger
    if _cost_logger is None:
        _cost_logger = ObservabilityService()
    return _cost_logger


def get_pattern_chain(llm_provider=None, search_service=None) -> PatternAnalysisChain:
    """Create pattern analysis chain with injected dependencies."""
    llm = llm_provider or get_llm_provider()
    search = search_service if search_service is not None else get_search_service()
    use_rag = search is not None
    return PatternAnalysisChain(llm_provider=llm, search_service=search, use_rag=use_rag)


def get_cost_chain(llm_provider=None, search_service=None) -> CostOptimizationChain:
    """Create cost optimization chain with injected dependencies."""
    llm = llm_provider or get_llm_provider()
    search = search_service if search_service is not None else get_search_service()
    use_rag = search is not None
    return CostOptimizationChain(llm_provider=llm, search_service=search, use_rag=use_rag)


def get_explanation_chain(llm_provider=None) -> ExplanationChain:
    """Create explanation chain with injected dependencies."""
    llm = llm_provider or get_llm_provider()
    return ExplanationChain(llm_provider=llm)


def _get_cluster_config_deps():
    """Deps for ClusterConfigAgent - used by agent factory."""
    return {
        "pattern_chain": get_pattern_chain(),
        "cost_chain": get_cost_chain(),
        "explanation_chain": get_explanation_chain(),
        "cost_logger": get_cost_logger(),
        "search_service": get_search_service(),
    }


def get_recommendation_agent(overrides: Optional[dict] = None):
    """Get cluster config agent. Uses registry; cached when using defaults.
    For the recommendation API use Depends(get_recommendation_agent_dep). For tests, call with overrides dict.
    """
    global _cluster_config_agent
    if overrides:
        deps = _get_cluster_config_deps()
        deps.update(overrides)
        return create_agent("cluster_config", **deps)
    if _cluster_config_agent is not None:
        return _cluster_config_agent
    _cluster_config_agent = create_agent(
        "cluster_config",
        **_get_cluster_config_deps(),
    )
    return _cluster_config_agent


def get_recommendation_agent_dep():
    """Dependency for recommendation route: returns cached agent (no query/body params)."""
    return get_recommendation_agent()


def get_agent(agent_id: str, overrides: Optional[dict] = None):
    """Get agent by ID. Uses registry. Cached for cluster_config when no overrides."""
    if agent_id == "cluster_config":
        return get_recommendation_agent(overrides=overrides)
    # Future agents: add _get_<agent>_deps() and extend create_agent call
    raise KeyError(f"Unknown agent_id: {agent_id}. Available: {get_registered_agent_ids()}")


def reset_dependencies():
    """Reset cached singletons (for testing)."""
    global _llm_provider, _search_service, _cost_logger, _cluster_config_agent
    _llm_provider = None
    _search_service = None
    _cost_logger = None
    _cluster_config_agent = None
