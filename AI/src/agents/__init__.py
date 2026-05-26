"""AI agents — import packages to trigger registration."""

from AI.src.agents import job_run_cluster_sizing  # noqa: F401
from AI.src.core.registry import (
    AGENT_ALIASES,
    AGENT_DEPS_FACTORIES,
    AGENT_REGISTRY,
    create_agent,
    get_agent_class,
    get_registered_agent_ids,
    register_agent,
)

__all__ = [
    "AGENT_REGISTRY",
    "AGENT_DEPS_FACTORIES",
    "AGENT_ALIASES",
    "get_agent_class",
    "get_registered_agent_ids",
    "create_agent",
    "register_agent",
    "job_run_cluster_sizing",
]
