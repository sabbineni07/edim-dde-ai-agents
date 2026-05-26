"""Protocol for RAG historical context used by agent sizing chains."""

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
        """Context for sizing: similar job utilization patterns (legacy name)."""
        ...

    def sizing_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        """Context for cluster sizing LLM: similar job utilization patterns."""
        ...
