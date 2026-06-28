"""Mock LLM service for local testing without Azure OpenAI."""

import json
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MERGED_SIZING_JSON = json.dumps(
    {
        "pattern_analysis": (
            "### 1. Workload type\n"
            "- ETL workload from ingest metrics.\n\n"
            "### 2. Resource utilization\n"
            "- CPU and memory utilization support right-sizing.\n\n"
            "### 3. Performance characteristics\n"
            "- Stable node consumption patterns.\n\n"
            "### 4. Optimization opportunities\n"
            "- Align max_workers with p95 nodes plus buffer."
        ),
        "node_family": "E",
        "vcpus": 4,
        "min_workers": 2,
        "max_workers": 8,
        "auto_termination_minutes": 0,
        "rationale": (
            "Based on utilization patterns; max_workers aligned to observed nodes. "
            "auto_termination_minutes 0 for immediate cluster termination when the job completes."
        ),
    }
)


class MockChatModel(BaseChatModel):
    """Mock chat model for local testing."""

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        prompt_text = str(messages[-1].content) if messages else ""

        if "pattern_analysis" in prompt_text and "node_family" in prompt_text:
            response = _MERGED_SIZING_JSON
        elif "cost" in prompt_text.lower() or "optimize" in prompt_text.lower():
            response = _MERGED_SIZING_JSON
        elif "pattern" in prompt_text.lower() or "analyze" in prompt_text.lower():
            response = json.loads(_MERGED_SIZING_JSON)["pattern_analysis"]
        elif "explain" in prompt_text.lower() or "explanation" in prompt_text.lower():
            response = (
                "This recommendation is based on analysis of historical job execution metrics. "
                "The recommended configuration maintains performance while improving utilization."
            )
        elif "Retrieved context:" in prompt_text or "User question:" in prompt_text:
            response = (
                "Based on the retrieved knowledge index context (mock LLM). "
                "Configure USE_MOCK_LLM=false and valid Foundry credentials for real answers."
            )
        else:
            response = "Mock LLM response for local testing."

        message = AIMessage(content=response)
        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "mock"


class MockLLMService:
    """Mock LLM service for local testing."""

    def __init__(self):
        self.llm = MockChatModel()
        logger.info("mock_llm_service_initialized")

    def get_llm(self):
        return self.llm

    def get_embeddings(self):
        return None
