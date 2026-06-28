"""Chat API: connection-scoped LLM + optional RAG over Azure Search / FAISS."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from AI.src.core.llm.foundry_llm_service import FoundryLLMNotConfiguredError, FoundryLLMService
from AI.src.core.llm.mock_llm_service import MockLLMService
from AI.src.core.retrieval.chat_retriever import format_chunks_for_prompt, retrieve_for_chat
from shared.config.chat_settings_resolver import resolve_chat_settings
from shared.services.platform_environment_service import get_environment
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

_CHAT_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions using the retrieved context from "
    "the user's selected knowledge index. The index may contain documents from any domain. "
    "Answer using ONLY the retrieved context. If the context is empty or insufficient, "
    "say so clearly and do not guess. When citing facts, reference source numbers like [1], [2]. "
    "Do not invent facts, identifiers, or figures that are not supported by the context. "
    "Format answers using Markdown when helpful (headings, bullet lists, bold, code blocks)."
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    environment_id: str = Field(..., min_length=1)
    llm_connection_id: str = Field(..., min_length=1)
    rag_connection_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class ChatSource(BaseModel):
    id: str
    document_type: str
    score: Optional[float] = None
    excerpt: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    sources: List[ChatSource]
    context_summary: Dict[str, Any]


def _use_mock_llm() -> bool:
    return os.environ.get("USE_MOCK_LLM", "").lower() in ("true", "1", "yes")


def _get_chat_llm(settings):
    if _use_mock_llm():
        logger.info("chat_using_mock_llm")
        return MockLLMService().get_llm()
    svc = FoundryLLMService(config=settings)
    return svc.get_llm()


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Answer a question using the selected Foundry LLM and optional knowledge index."""
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    if not get_environment(req.environment_id):
        raise HTTPException(status_code=404, detail="Environment not found")

    from uuid import UUID

    try:
        llm_uuid = UUID(req.llm_connection_id)
        rag_uuid = UUID(req.rag_connection_id) if req.rag_connection_id else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid connection id") from e

    try:
        settings, conn_meta = resolve_chat_settings(
            environment_id=req.environment_id,
            llm_connection_id=llm_uuid,
            rag_connection_id=rag_uuid,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    chunks = retrieve_for_chat(settings, question, top_k=req.top_k)
    context_text = format_chunks_for_prompt(chunks)

    try:
        llm = _get_chat_llm(settings)
    except FoundryLLMNotConfiguredError as e:
        logger.error("chat_foundry_llm_not_configured", error=str(e))
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("chat_foundry_llm_init_error", error=str(e))
        raise HTTPException(status_code=500, detail="LLM not available") from e

    user_content = f"Retrieved context:\n{context_text}\n\n" f"User question: {question}"

    try:
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]
        )
        answer_text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        logger.error("chat_llm_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate answer") from e

    sources = [
        ChatSource(
            id=c.id or f"chunk-{i}",
            document_type=c.document_type,
            score=c.score,
            excerpt=c.excerpt(),
            metadata=c.metadata,
        )
        for i, c in enumerate(chunks, start=1)
    ]

    return ChatResponse(
        answer=answer_text,
        sources=sources,
        context_summary={
            **conn_meta,
            "source_count": len(sources),
            "top_k": req.top_k,
            "mock_llm": _use_mock_llm(),
        },
    )
