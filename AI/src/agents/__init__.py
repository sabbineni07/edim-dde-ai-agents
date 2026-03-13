"""AI agents - registry and agent implementations.

Import agent subpackages to trigger registration.
"""

# Trigger registration of all agents (import causes @register_agent to run)
from AI.src.agents import cluster_config  # noqa: F401
from AI.src.agents.registry import (
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
    "get_agent_class",
    "get_registered_agent_ids",
    "create_agent",
    "register_agent",
    "cluster_config",
]
