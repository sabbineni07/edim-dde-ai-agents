"""Types for connection-scoped chat retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RetrievedChunk:
    """A single RAG hit passed to the chat LLM prompt."""

    id: str
    content: str
    document_type: str
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def excerpt(self, max_len: int = 400) -> str:
        text = (self.content or "").strip().replace("\n", " ")
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."
