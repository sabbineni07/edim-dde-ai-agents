"""Mock LLM service for local testing without Azure OpenAI."""

from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from shared.utils.logging import get_logger

logger = get_logger(__name__)


class MockChatModel(BaseChatModel):
    """Mock chat model for local testing."""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a mock response."""
        # Simple mock response based on the input
        prompt_text = str(messages[-1].content) if messages else ""

        # Generate context-aware mock responses
        if "pattern" in prompt_text.lower() or "analyze" in prompt_text.lower():
            response = """Based on the job metrics provided, this workload shows:
1. Workload Type: ETL processing with moderate complexity
2. Resource Utilization: CPU utilization averages 45-48%, Memory utilization 60-65%
3. Performance Characteristics: Consistent execution times around 3600-3900 seconds
4. Optimization Opportunities: Current configuration appears well-suited, but could benefit from right-sizing based on actual node consumption patterns."""
        elif "cost" in prompt_text.lower() or "optimize" in prompt_text.lower():
            response = """{"node_family": "E", "vcpus": 4, "min_workers": 2, "max_workers": 8, "auto_termination_minutes": 30, "rationale": "Based on utilization patterns showing average 4-5 nodes consumed, recommending E4s_v3 with 2-8 workers for better cost efficiency"}"""
        elif "explain" in prompt_text.lower() or "explanation" in prompt_text.lower():
            response = """This recommendation is based on analysis of historical job execution metrics. The current cluster configuration shows:
- Average node consumption: 4-5 nodes
- Peak utilization: CPU 78-81%, Memory 89-92%
- The recommended configuration maintains performance while reducing costs through better resource alignment."""
        else:
            response = "Mock LLM response for local testing. This is a placeholder response."

        message = AIMessage(content=response)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        """Return the LLM type."""
        return "mock"


class MockLLMService:
    """Mock LLM service for local testing."""

    def __init__(self):
        """Initialize mock LLM service."""
        self.llm = MockChatModel()
        logger.info("mock_llm_service_initialized")

    def get_llm(self):
        """Get the mock LLM instance."""
        return self.llm

    def get_embeddings(self):
        """Get mock embeddings (returns None for now)."""
        return None
