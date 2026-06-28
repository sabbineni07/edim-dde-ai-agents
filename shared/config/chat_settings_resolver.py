"""Resolve effective Settings for Chat from environment connection picks."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from uuid import UUID

from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.config.connection_credentials import resolve_connection_secrets
from shared.config.loader import get_agent_settings
from shared.config.settings import Settings
from shared.config.workspace_settings_resolver import _connection_to_settings_flat
from shared.services.environment_connection_service import EnvironmentConnectionService

_LLM_TYPES = frozenset({"ai_foundry"})
_RAG_TYPES = frozenset({"ai_search", "faiss"})


def _require_connection(
    svc: EnvironmentConnectionService,
    connection_id: UUID,
    *,
    environment_id: str,
    allowed_types: frozenset[str],
    label: str,
):
    rec = svc.get_connection(connection_id)
    if not rec:
        raise LookupError(f"{label} connection not found")
    if rec.environment_id != environment_id:
        raise ValueError(f"{label} connection does not belong to environment {environment_id}")
    if rec.connection_type not in allowed_types:
        raise ValueError(
            f"{label} connection must be one of {sorted(allowed_types)}; got {rec.connection_type}"
        )
    return rec


def resolve_chat_settings(
    *,
    environment_id: str,
    llm_connection_id: UUID,
    rag_connection_id: Optional[UUID] = None,
) -> Tuple[Settings, Dict[str, Any]]:
    """Build Settings for chat from explicit LLM and optional RAG environment connections."""
    eid = (environment_id or "").strip()
    if not eid:
        raise ValueError("environment_id is required")

    svc = EnvironmentConnectionService()
    llm_rec = _require_connection(
        svc,
        llm_connection_id,
        environment_id=eid,
        allowed_types=_LLM_TYPES,
        label="LLM",
    )

    flat: Dict[str, Any] = {}
    secrets: Dict[str, Any] = {}
    flat.update(_connection_to_settings_flat(llm_rec.connection_type, llm_rec.config or {}))
    secrets.update(
        resolve_connection_secrets(llm_rec.connection_type, llm_rec.id, llm_rec.config or {})
    )

    rag_meta: Dict[str, Any] = {"rag_connection_id": None, "rag_connection_type": None}
    if rag_connection_id:
        rag_rec = _require_connection(
            svc,
            rag_connection_id,
            environment_id=eid,
            allowed_types=_RAG_TYPES,
            label="RAG",
        )
        flat.update(_connection_to_settings_flat(rag_rec.connection_type, rag_rec.config or {}))
        secrets.update(
            resolve_connection_secrets(rag_rec.connection_type, rag_rec.id, rag_rec.config or {})
        )
        rag_meta = {
            "rag_connection_id": str(rag_rec.id),
            "rag_connection_type": rag_rec.connection_type,
        }
    else:
        flat["vector_retrieval_backend"] = "none"

    settings = get_agent_settings(
        DBX_CLUSTER_TUNING_AGENT_ID,
        overrides=flat,
        secrets=secrets,
    )
    meta = {
        "environment_id": eid,
        "llm_connection_id": str(llm_rec.id),
        "llm_connection_type": llm_rec.connection_type,
        **rag_meta,
    }
    return settings, meta
