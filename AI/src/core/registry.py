"""Agent registry for discovery and factory creation."""

from typing import Any, Callable, Dict, Type

from shared.utils.logging import get_logger

logger = get_logger(__name__)

AGENT_REGISTRY: Dict[str, Type] = {}
AGENT_DEPS_FACTORIES: Dict[str, Callable[[], Dict[str, Any]]] = {}


def register_agent(
    agent_id: str,
    deps_factory: Callable[[], Dict[str, Any]] = None,
):
    """Register an agent class and optional dependency factory."""

    def decorator(cls: Type) -> Type:
        AGENT_REGISTRY[agent_id] = cls
        if deps_factory is not None:
            AGENT_DEPS_FACTORIES[agent_id] = deps_factory
        logger.info("agent_registered", agent_id=agent_id, class_name=cls.__name__)
        return cls

    return decorator


def get_agent_class(agent_id: str) -> Type:
    if agent_id not in AGENT_REGISTRY:
        available = ", ".join(sorted(AGENT_REGISTRY.keys()))
        raise KeyError(f"Unknown agent_id: '{agent_id}'. Available: {available}")
    return AGENT_REGISTRY[agent_id]


def get_registered_agent_ids() -> list:
    return sorted(AGENT_REGISTRY.keys())


def create_agent(agent_id: str, **overrides) -> Any:
    cls = get_agent_class(agent_id)
    deps = {}
    if agent_id in AGENT_DEPS_FACTORIES:
        deps = AGENT_DEPS_FACTORIES[agent_id]()
    deps.update(overrides)
    return cls(**deps)
