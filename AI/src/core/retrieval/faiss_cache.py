"""Process-level FAISS index cache and append helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from langchain_core.documents import Document

from AI.src.core.retrieval.faiss_provider import load_faiss_vectorstore
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_cache: Dict[str, Tuple[float, Any]] = {}


def faiss_index_mtime(index_folder: str) -> float:
    path = Path(index_folder)
    if not path.is_dir():
        return 0.0
    mtimes = [item.stat().st_mtime for item in path.iterdir() if item.is_file()]
    return max(mtimes) if mtimes else 0.0


def load_cached_faiss_vectorstore(index_folder: str, embeddings: Any) -> Any:
    """Load FAISS from disk once per path until the index folder mtime changes."""
    mtime = faiss_index_mtime(index_folder)
    cached = _cache.get(index_folder)
    if cached and cached[0] == mtime:
        return cached[1]

    vs = load_faiss_vectorstore(index_folder, embeddings)
    _cache[index_folder] = (mtime, vs)
    logger.debug("faiss_cache_loaded", path=index_folder, mtime=mtime)
    return vs


def invalidate_faiss_cache(index_folder: Optional[str] = None) -> None:
    if index_folder:
        _cache.pop(index_folder, None)
    else:
        _cache.clear()


def append_to_faiss_index(index_folder: str, embeddings: Any, document: Document) -> None:
    """Append one document to a local FAISS index and invalidate the read cache."""
    from langchain_community.vectorstores import FAISS

    path = Path(index_folder)
    index_file = path / "index.faiss"

    if index_file.exists():
        vs = load_faiss_vectorstore(str(path), embeddings)
        vs.add_documents([document])
    else:
        path.mkdir(parents=True, exist_ok=True)
        vs = FAISS.from_documents([document], embeddings)

    vs.save_local(str(path))
    invalidate_faiss_cache(str(path))
    logger.info("faiss_index_appended", path=str(path))
