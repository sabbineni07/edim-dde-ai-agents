"""Protocol for RAG historical context used by pattern and cost chains."""

from typing import Dict, Protocol, runtime_checkable


@runtime_checkable
class RagContextProvider(Protocol):
    """Builds optional text context for LLM prompts from a vector store (Azure or FAISS)."""

    def cost_chain_historical_context(
        self, pattern_analysis: str, job_cluster_metrics: Dict
    ) -> str:
        """Context for cost optimization: similar recommendations and/or job patterns."""
        ...

    def pattern_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        """Context for pattern analysis: similar job utilization patterns."""
        ...
