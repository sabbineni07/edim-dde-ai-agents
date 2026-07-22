"""AI agents — import packages to trigger registration."""

from AI.src.agents import dbx_cluster_tuning_agent  # noqa: F401
from AI.src.agents import spark_job_rca_agent  # noqa: F401
from AI.src.core.registry import (
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
    "dbx_cluster_tuning_agent",
    "spark_job_rca_agent",
]
