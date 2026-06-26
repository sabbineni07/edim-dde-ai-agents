"""Index approved recommendations into Azure AI Search or local FAISS."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from shared.config.loader import get_agent_settings
from shared.config.rag_settings import is_rag_enabled, rag_backend
from shared.config.settings import Settings
from shared.rag.approved_document import (
    build_approved_index_payload,
    build_approved_retrieval_text,
    build_faiss_metadata,
)
from shared.rag.embeddings import embeddings_from_settings
from shared.recommendation_lifecycle import LIFECYCLE_APPROVED
from shared.utils.logging import get_logger

logger = get_logger(__name__)

try:
    from shared.database.connection import get_database_session
    from shared.database.models import (
        RecommendationHistory,
        RecommendationLifecycleEvent,
        RequestLog,
    )

    DATABASE_AVAILABLE = True
except Exception as e:
    logger.warning("approved_indexing_database_import_failed", error=str(e))
    DATABASE_AVAILABLE = False


def resolve_rag_settings_for_history(rec: Any) -> Optional[Settings]:
    """Resolve effective Settings for RAG indexing from history + request log."""
    from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
    from shared.services.workspace_agent_service import WorkspaceAgentService

    workspace_agent_id: Optional[str] = None
    if DATABASE_AVAILABLE and rec.request_log_request_id:
        session = get_database_session()
        try:
            req = (
                session.query(RequestLog)
                .filter(RequestLog.request_id == rec.request_log_request_id)
                .first()
            )
            if req and isinstance(req.request_params, dict):
                workspace_agent_id = req.request_params.get("workspace_agent_id")
        finally:
            session.close()

    svc = WorkspaceAgentService()
    if workspace_agent_id:
        try:
            _agent_id, flat, secrets = svc.resolve_settings_for_agent(UUID(str(workspace_agent_id)))
            return get_agent_settings(_agent_id, overrides=flat, secrets=secrets)
        except (LookupError, ValueError) as e:
            logger.warning(
                "approved_indexing_workspace_agent_resolve_failed",
                workspace_agent_id=workspace_agent_id,
                error=str(e),
            )

    if rec.workspace_id:
        agents = svc.list_agents(
            workspace_id=rec.workspace_id,
            agent_id=DBX_CLUSTER_TUNING_AGENT_ID,
        )
        for agent in agents:
            if (agent.bindings or {}).get("rag"):
                try:
                    _agent_id, flat, secrets = svc.resolve_settings_for_agent(agent.id)
                    return get_agent_settings(_agent_id, overrides=flat, secrets=secrets)
                except (LookupError, ValueError):
                    continue

    return None


def index_approved_recommendation(request_id: UUID) -> bool:
    """Index a recommendation after lifecycle reaches APPROVED. No-op when RAG is off."""
    if not DATABASE_AVAILABLE:
        logger.info("approved_indexing_skipped", reason="database_unavailable")
        return False

    session = get_database_session()
    try:
        rec = (
            session.query(RecommendationHistory)
            .filter(RecommendationHistory.request_id == request_id)
            .first()
        )
        if not rec:
            logger.warning("approved_indexing_not_found", request_id=str(request_id))
            return False

        if (rec.lifecycle_status or "").upper() != LIFECYCLE_APPROVED:
            logger.info(
                "approved_indexing_skipped",
                request_id=str(request_id),
                lifecycle_status=rec.lifecycle_status,
            )
            return False

        settings = resolve_rag_settings_for_history(rec)
        if settings is None or not is_rag_enabled(settings):
            logger.info(
                "approved_indexing_skipped",
                request_id=str(request_id),
                reason="rag_disabled_or_unbound",
            )
            return False

        backend = rag_backend(settings)
        lifecycle_events = (
            session.query(RecommendationLifecycleEvent)
            .filter(RecommendationLifecycleEvent.request_id == request_id)
            .order_by(RecommendationLifecycleEvent.changed_at.asc())
            .all()
        )
        retrieval_text = build_approved_retrieval_text(rec, lifecycle_events=lifecycle_events)
        if not retrieval_text:
            logger.warning("approved_indexing_empty_text", request_id=str(request_id))
            return False

        payload = build_approved_index_payload(rec)

        if backend == "azure_search":
            return _index_to_azure_search(settings, payload, retrieval_text)
        if backend == "faiss":
            return _index_to_faiss(settings, rec, payload, retrieval_text)
        logger.info("approved_indexing_skipped", backend=backend, request_id=str(request_id))
        return False
    finally:
        session.close()


def _index_to_azure_search(settings: Settings, payload: dict, retrieval_text: str) -> bool:
    from AI.src.core.llm.azure_search_service import create_search_service

    search = create_search_service(settings)
    if search is None:
        logger.warning("approved_indexing_azure_search_unavailable")
        return False
    return search.index_approved_document(payload, retrieval_text)


def _index_to_faiss(settings: Settings, rec: Any, payload: dict, retrieval_text: str) -> bool:
    from langchain_core.documents import Document

    from AI.src.core.retrieval.faiss_cache import append_to_faiss_index

    path = (settings.faiss_index_path or "").strip()
    if not path:
        logger.warning("approved_indexing_faiss_missing_path")
        return False

    try:
        embeddings = embeddings_from_settings(settings)
    except Exception as e:
        logger.warning("approved_indexing_embeddings_failed", error=str(e))
        return False

    metadata = build_faiss_metadata(rec, payload, retrieval_text)
    doc = Document(page_content=retrieval_text, metadata=metadata)
    append_to_faiss_index(path, embeddings, doc)
    logger.info("approved_indexing_faiss_complete", request_id=str(rec.request_id), path=path)
    return True
