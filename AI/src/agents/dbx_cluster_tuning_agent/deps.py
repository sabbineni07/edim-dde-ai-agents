"""Dependency wiring for the DBX cluster tuning agent."""

from AI.src.agents.dbx_cluster_tuning_agent.chains.explanation import RecommendationExplanationChain
from AI.src.agents.dbx_cluster_tuning_agent.chains.sizing import ClusterSizingChain
from AI.src.core.platform import (
    get_cost_logger,
    get_llm_provider,
    get_rag_context_provider,
    get_search_service,
)
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.config.loader import get_agent_settings

AGENT_ID = DBX_CLUSTER_TUNING_AGENT_ID


def get_sizing_chain(
    llm_provider=None, rag_provider=None, agent_id: str = AGENT_ID
) -> ClusterSizingChain:
    llm = llm_provider or get_llm_provider()
    agent_settings = get_agent_settings(agent_id)
    if rag_provider is None:
        backend = (agent_settings.vector_retrieval_backend or "azure_search").strip().lower()
        rag_provider = get_rag_context_provider() if backend != "none" else None
    use_rag = rag_provider is not None and (
        (agent_settings.vector_retrieval_backend or "").strip().lower() != "none"
    )
    return ClusterSizingChain(
        llm_provider=llm,
        rag_provider=rag_provider,
        use_rag=use_rag,
        settings=agent_settings,
    )


def get_explanation_chain(llm_provider=None) -> RecommendationExplanationChain:
    llm = llm_provider or get_llm_provider()
    return RecommendationExplanationChain(llm_provider=llm)


def get_dbx_cluster_tuning_agent_deps(agent_id: str = AGENT_ID) -> dict:
    """Kwargs for DbxClusterTuningAgent.__init__."""
    return {
        "sizing_chain": get_sizing_chain(agent_id=agent_id),
        "explanation_chain": get_explanation_chain(),
        "cost_logger": get_cost_logger(),
        "search_service": get_search_service(),
        "settings": get_agent_settings(agent_id),
    }
