"""Platform singletons shared by all agents (LLM, search, RAG)."""

import os
from typing import Any, Optional

from AI.src.core.llm.azure_search_service import AzureSearchService, create_search_service
from AI.src.core.llm.foundry_llm_service import FoundryLLMService
from AI.src.core.llm.mock_llm_service import MockLLMService
from AI.src.core.retrieval import create_rag_context_provider
from shared.config.loader import get_platform_settings
from shared.config.rag_settings import is_rag_enabled
from shared.services.observability_service import ObservabilityService
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_llm_provider: Optional[Any] = None
_search_service: Optional[AzureSearchService] = None
_rag_context_provider: Optional[Any] = None
_cost_logger: Optional[ObservabilityService] = None


def use_mock_llm() -> bool:
    """True when USE_MOCK_LLM is enabled (local/dev without Azure OpenAI)."""
    return os.environ.get("USE_MOCK_LLM", "").lower() in ("true", "1", "yes")


def get_llm_provider():
    """Azure AI Foundry or mock when USE_MOCK_LLM=true."""
    global _llm_provider
    if _llm_provider is None:
        if use_mock_llm():
            _llm_provider = MockLLMService()
            logger.info("using_mock_llm_provider")
        else:
            _llm_provider = FoundryLLMService()
    return _llm_provider


def get_search_service() -> Optional[AzureSearchService]:
    global _search_service
    if _search_service is None:
        plat = get_platform_settings()
        if not is_rag_enabled(plat):
            return None
        try:
            _search_service = create_search_service(plat)
        except Exception as e:
            logger.warning("search_service_unavailable", error=str(e))
            _search_service = None
    return _search_service


def get_rag_context_provider():
    global _rag_context_provider
    if _rag_context_provider is None:
        _rag_context_provider = create_rag_context_provider(
            get_platform_settings(), get_llm_provider, get_search_service
        )
    return _rag_context_provider


def get_cost_logger() -> ObservabilityService:
    global _cost_logger
    if _cost_logger is None:
        _cost_logger = ObservabilityService()
    return _cost_logger


def reset_platform_singletons():
    """Reset cached singletons (tests)."""
    global _llm_provider, _search_service, _rag_context_provider, _cost_logger
    _llm_provider = None
    _search_service = None
    _rag_context_provider = None
    _cost_logger = None
