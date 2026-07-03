"""Create RagContextProvider from settings (Azure AI Search, FAISS, or disabled)."""

from typing import Any, Callable, Optional

from AI.src.core.retrieval.azure_provider import AzureSearchRagProvider
from AI.src.core.retrieval.faiss_cache import load_cached_faiss_vectorstore
from AI.src.core.retrieval.faiss_provider import FaissRagProvider
from AI.src.core.retrieval.protocol import RagContextProvider
from shared.config.llm_sampling import resolve_rag_top_k
from shared.config.rag_settings import is_rag_enabled, rag_backend
from shared.config.settings import Settings
from shared.rag.faiss_paths import resolve_faiss_index_path_from_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def create_rag_context_provider(
    settings: Settings,
    get_llm_provider: Callable[[], Any],
    get_search_service: Callable[[], Any],
) -> Optional[RagContextProvider]:
    """Build retrieval provider for pattern/cost chains. Returns None when RAG is off or unavailable."""
    backend = rag_backend(settings)

    if not is_rag_enabled(settings):
        logger.info("rag_context_provider_disabled", backend=backend)
        return None

    top_rec, top_jobs = resolve_rag_top_k(settings)

    if backend == "azure_search":
        try:
            svc = get_search_service()
        except Exception as e:
            logger.warning("rag_azure_search_unavailable", error=str(e))
            return None
        if svc is None:
            logger.info("rag_context_provider_skipped", reason="azure_search_not_configured")
            return None
        return AzureSearchRagProvider(svc, top_k_recommendations=top_rec, top_k_jobs=top_jobs)

    if backend == "faiss":
        path = resolve_faiss_index_path_from_settings(settings)
        if not path:
            logger.warning(
                "rag_faiss_missing_path", hint="Set faiss_index_path on the FAISS connection"
            )
            return None
        try:
            from AI.src.core.llm.chat_model_factory import can_create_chat_model
            from shared.rag.embeddings import embeddings_from_settings

            if can_create_chat_model(settings):
                emb = embeddings_from_settings(settings)
            else:
                llm = get_llm_provider()
                emb = llm.get_embeddings()
            if emb is None:
                logger.warning("rag_faiss_no_embeddings")
                return None
            vs = load_cached_faiss_vectorstore(path, emb)
            logger.info(
                "rag_context_provider_ready",
                backend="faiss",
                path=path,
                storage_type=settings.faiss_storage_type,
            )
            return FaissRagProvider(vs, top_k_recommendations=top_rec, top_k_jobs=top_jobs)
        except Exception as e:
            logger.warning("rag_faiss_load_failed", path=path, error=str(e))
            return None

    logger.warning("rag_unknown_backend", backend=backend)
    return None
