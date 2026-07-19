"""FastAPI dependency injection — platform singletons and agent factory."""

from typing import Any, Optional

from AI.src.agents import dbx_cluster_tuning_agent  # noqa: F401 - register agents
from AI.src.agents import spark_job_rca_agent  # noqa: F401 - register agents
from AI.src.agents.dbx_cluster_tuning_agent import AGENT_ID
from AI.src.core.platform import (
    get_cost_logger,
    get_llm_provider,
    get_rag_context_provider,
    get_search_service,
    reset_platform_singletons,
)
from AI.src.core.registry import create_agent, get_registered_agent_ids
from shared.config.loader import reset_settings_cache
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_agent_cache: dict[str, Any] = {}


def get_agent(agent_id: str = AGENT_ID, overrides: Optional[dict] = None):
    """Create or return cached agent by registry id (default: dbx_cluster_tuning_agent)."""
    if overrides:
        return create_agent(agent_id, **overrides)
    if agent_id not in _agent_cache:
        _agent_cache[agent_id] = create_agent(agent_id)
    return _agent_cache[agent_id]


def get_recommendation_agent(overrides: Optional[dict] = None):
    """DBX cluster tuning agent (registry id dbx_cluster_tuning_agent)."""
    return get_agent(AGENT_ID, overrides=overrides)


def get_recommendation_agent_dep():
    """FastAPI Depends() entry for recommendation routes."""
    return get_recommendation_agent()


def get_rca_agent(overrides: Optional[dict] = None):
    """Spark job RCA agent."""
    from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID

    return get_agent(SPARK_JOB_RCA_AGENT_ID, overrides=overrides)


def reset_dependencies():
    """Reset cached singletons (tests)."""
    _agent_cache.clear()
    reset_platform_singletons()
    reset_settings_cache()


__all__ = [
    "get_llm_provider",
    "get_search_service",
    "get_rag_context_provider",
    "get_cost_logger",
    "get_agent",
    "get_recommendation_agent",
    "get_recommendation_agent_dep",
    "get_rca_agent",
    "get_registered_agent_ids",
    "reset_dependencies",
]
