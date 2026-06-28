"""Tests for chat retrieval helpers."""

from AI.src.core.retrieval.chat_retriever import format_chunks_for_prompt
from AI.src.core.retrieval.chat_types import RetrievedChunk


def test_format_chunks_empty():
    assert "No relevant documents" in format_chunks_for_prompt([])


def test_format_chunks_with_sources():
    text = format_chunks_for_prompt(
        [
            RetrievedChunk(
                id="doc-1",
                content="Job 123 had high CPU.",
                document_type="job_cluster_metrics",
                score=0.91,
            )
        ]
    )
    assert "Source [1]" in text
    assert "doc-1" in text
    assert "high CPU" in text
