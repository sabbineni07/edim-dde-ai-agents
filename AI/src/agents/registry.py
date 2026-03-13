"""Agent registry for discovery and factory creation."""

from typing import Any, Callable, Dict, Type

from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Agent ID -> Agent class
AGENT_REGISTRY: Dict[str, Type] = {}

# Agent ID -> deps factory (returns dict of kwargs for agent constructor)
AGENT_DEPS_FACTORIES: Dict[str, Callable[[], Dict[str, Any]]] = {}


def register_agent(agent_id: str, deps_factory: Callable[[], Dict[str, Any]] = None):
    """Decorator to register an agent class with the registry.

    Args:
        agent_id: Unique identifier (e.g. "cluster_config", "failure_rca")
        deps_factory: Optional callable that returns kwargs for agent __init__

    Example:
        @register_agent("cluster_config", deps_factory=get_cluster_config_deps)
        class ClusterConfigAgent: ...
    """

    def decorator(cls: Type) -> Type:
        AGENT_REGISTRY[agent_id] = cls
        if deps_factory is not None:
            AGENT_DEPS_FACTORIES[agent_id] = deps_factory
        logger.info("agent_registered", agent_id=agent_id, class_name=cls.__name__)
        return cls

    return decorator


def get_agent_class(agent_id: str) -> Type:
    """Get agent class by ID."""
    if agent_id not in AGENT_REGISTRY:
        available = ", ".join(sorted(AGENT_REGISTRY.keys()))
        raise KeyError(f"Unknown agent_id: '{agent_id}'. Available: {available}")
    return AGENT_REGISTRY[agent_id]


def get_registered_agent_ids() -> list:
    """Return sorted list of registered agent IDs."""
    return sorted(AGENT_REGISTRY.keys())


def create_agent(agent_id: str, **overrides) -> Any:
    """Create agent instance with injected dependencies.

    Args:
        agent_id: Registered agent ID
        **overrides: Override any dep (for testing)

    Returns:
        Agent instance
    """
    cls = get_agent_class(agent_id)
    deps = {}
    if agent_id in AGENT_DEPS_FACTORIES:
        deps = AGENT_DEPS_FACTORIES[agent_id]()
    deps.update(overrides)
    return cls(**deps)
