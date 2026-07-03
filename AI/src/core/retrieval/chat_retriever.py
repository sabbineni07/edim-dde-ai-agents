"""Question-driven retrieval for Chat (Azure AI Search or FAISS)."""

from __future__ import annotations

from typing import Any, List

from AI.src.core.llm.azure_search_service import AzureSearchService, create_search_service
from AI.src.core.llm.foundry_llm_service import FoundryLLMService
from AI.src.core.retrieval.chat_types import RetrievedChunk
from AI.src.core.retrieval.faiss_cache import load_cached_faiss_vectorstore
from shared.config.llm_sampling import resolve_rag_top_k
from shared.config.rag_settings import is_rag_enabled, rag_backend
from shared.config.settings import Settings
from shared.rag.faiss_paths import resolve_faiss_index_path_from_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _chunk_from_azure_hit(hit: Any) -> RetrievedChunk:
    md = dict(hit) if hasattr(hit, "keys") else {}
    content = (md.get("content") or "").strip()
    if not content and md.get("recommendation"):
        content = str(md.get("recommendation"))[:4000]
    doc_type = md.get("document_type") or (
        "recommendation" if md.get("is_recommendation") else "unknown"
    )
    score = md.get("@search.score")
    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
    return RetrievedChunk(
        id=str(md.get("id") or ""),
        content=content,
        document_type=str(doc_type),
        score=score,
        metadata={
            k: md.get(k)
            for k in ("job_id", "job_run_id", "workspace_id", "workload_type", "config_quality")
            if md.get(k) is not None
        },
    )


def _chunk_from_faiss_doc(doc: Any, score: float | None) -> RetrievedChunk:
    md = doc.metadata or {}
    content = (doc.page_content or "").strip()
    doc_type = md.get("document_type") or "unknown"
    return RetrievedChunk(
        id=str(md.get("id") or md.get("job_id") or ""),
        content=content,
        document_type=str(doc_type),
        score=score,
        metadata={k: md[k] for k in ("job_id", "workspace_id", "workload_type") if k in md},
    )


def retrieve_for_chat(
    settings: Settings, question: str, *, top_k: int | None = None
) -> List[RetrievedChunk]:
    """Retrieve top-k chunks for a natural-language chat question."""
    q = (question or "").strip()
    if not q or not is_rag_enabled(settings):
        return []

    top_rec, top_jobs = resolve_rag_top_k(settings)
    k = top_k or max(top_rec + top_jobs, 5)
    backend = rag_backend(settings)

    if backend == "azure_search":
        svc = create_search_service(settings)
        if svc is None:
            svc = AzureSearchService(config=settings)
        if not svc.client:
            logger.warning("chat_retrieve_azure_unavailable")
            return []
        hits = svc.search_for_chat(q, top_k=k)
        out: List[RetrievedChunk] = []
        for h in hits:
            chunk = _chunk_from_azure_hit(h)
            if chunk.content:
                out.append(chunk)
        return out

    if backend == "faiss":
        path = resolve_faiss_index_path_from_settings(settings)
        if not path:
            logger.warning("chat_retrieve_faiss_missing_path")
            return []
        try:
            from AI.src.core.llm.chat_model_factory import can_create_chat_model
            from shared.rag.embeddings import embeddings_from_settings

            if can_create_chat_model(settings):
                emb = embeddings_from_settings(settings)
            else:
                emb = FoundryLLMService(config=settings).get_embeddings()
            vs = load_cached_faiss_vectorstore(
                path,
                emb,
                faiss_storage_type=settings.faiss_storage_type,
                databricks_server_hostname=settings.databricks_server_hostname,
            )
            pairs = vs.similarity_search_with_score(q, k=k)
            out: List[RetrievedChunk] = []
            for doc, raw_score in pairs:
                score = float(raw_score) if raw_score is not None else None
                chunk = _chunk_from_faiss_doc(doc, score)
                if chunk.content:
                    out.append(chunk)
            return out
        except Exception as e:
            logger.warning("chat_retrieve_faiss_failed", error=str(e))
            return []

    logger.warning("chat_retrieve_unknown_backend", backend=backend)
    return []


def format_chunks_for_prompt(chunks: List[RetrievedChunk]) -> str:
    """Serialize retrieved chunks for the LLM user message."""
    if not chunks:
        return "(No relevant documents were found in the knowledge index.)"
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        header = f"Source [{i}] type={chunk.document_type} id={chunk.id or 'n/a'}"
        if chunk.score is not None:
            header += f" score={chunk.score:.4f}"
        parts.append(f"{header}\n{chunk.content.strip()}")
    return "\n\n".join(parts)
