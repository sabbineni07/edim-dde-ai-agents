"""Protocol for RAG historical context used by agent sizing chains."""

from typing import Dict, Protocol, runtime_checkable


@runtime_checkable
class RagContextProvider(Protocol):
    """Builds optional text context for LLM prompts from a vector store (Azure or FAISS)."""

    def sizing_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        """Context for cluster sizing LLM: similar recommendations and job utilization patterns."""
        ...
