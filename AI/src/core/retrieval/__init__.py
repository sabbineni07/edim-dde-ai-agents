"""Config-driven RAG context for chains (Azure AI Search or FAISS)."""

from AI.src.core.retrieval.factory import create_rag_context_provider
from AI.src.core.retrieval.protocol import RagContextProvider

__all__ = ["create_rag_context_provider", "RagContextProvider"]
