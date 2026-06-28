"""Dependency wiring for the DBX cluster tuning agent."""

from typing import Any, Dict, Optional

from AI.src.agents.dbx_cluster_tuning_agent.chains.explanation import RecommendationExplanationChain
from AI.src.agents.dbx_cluster_tuning_agent.chains.sizing import ClusterSizingChain
from AI.src.core.llm.azure_search_service import create_search_service
from AI.src.core.platform import get_cost_logger, get_llm_provider
from AI.src.core.retrieval import create_rag_context_provider
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.config.loader import get_agent_settings
from shared.config.rag_settings import is_rag_enabled
from shared.config.settings import Settings

AGENT_ID = DBX_CLUSTER_TUNING_AGENT_ID


def get_sizing_chain(
    llm_provider=None,
    rag_provider=None,
    agent_id: str = AGENT_ID,
    settings: Optional[Settings] = None,
) -> ClusterSizingChain:
    agent_settings = settings or get_agent_settings(agent_id)
    if rag_provider is None and is_rag_enabled(agent_settings):
        rag_provider = create_rag_context_provider(
            agent_settings,
            get_llm_provider,
            lambda: create_search_service(agent_settings),
        )
    use_rag = rag_provider is not None and is_rag_enabled(agent_settings)
    return ClusterSizingChain(
        llm_provider=llm_provider,
        rag_provider=rag_provider,
        use_rag=use_rag,
        settings=agent_settings,
    )


def get_explanation_chain(
    llm_provider=None,
    settings: Optional[Settings] = None,
    agent_id: str = AGENT_ID,
) -> RecommendationExplanationChain:
    agent_settings = settings or get_agent_settings(agent_id)
    return RecommendationExplanationChain(llm_provider=llm_provider, settings=agent_settings)


def build_agent_runtime_deps(
    settings: Settings,
    agent_id: str = AGENT_ID,
) -> Dict[str, Any]:
    """Per-request agent parts that depend on effective settings (RAG on/off, Search endpoint)."""
    return {
        "sizing_chain": get_sizing_chain(agent_id=agent_id, settings=settings),
        "explanation_chain": get_explanation_chain(agent_id=agent_id, settings=settings),
        "search_service": create_search_service(settings),
    }


def get_dbx_cluster_tuning_agent_deps(agent_id: str = AGENT_ID) -> dict:
    """Kwargs for DbxClusterTuningAgent.__init__ (default YAML/platform settings)."""
    agent_settings = get_agent_settings(agent_id)
    return {
        **build_agent_runtime_deps(agent_settings, agent_id=agent_id),
        "cost_logger": get_cost_logger(),
        "settings": agent_settings,
    }
