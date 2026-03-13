"""Abstract interfaces (protocols) for dependency injection and testability."""

from shared.abstractions.protocols import (
    BaseAgent,
    CostLogger,
    DataCollector,
    LLMProvider,
    SearchService,
)

__all__ = ["BaseAgent", "LLMProvider", "SearchService", "DataCollector", "CostLogger"]
