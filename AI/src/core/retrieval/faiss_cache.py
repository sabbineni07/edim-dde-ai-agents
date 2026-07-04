"""Process-level FAISS index cache and append helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from langchain_core.documents import Document

from AI.src.core.retrieval.faiss_provider import load_faiss_vectorstore
from shared.rag.faiss_volume_storage import finalize_faiss_workspace, prepare_faiss_workspace
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_cache: Dict[str, Tuple[float, Any]] = {}


def _mtime_from_dir(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    mtimes = [item.stat().st_mtime for item in path.iterdir() if item.is_file()]
    return max(mtimes) if mtimes else 0.0


def faiss_index_mtime(
    index_folder: str,
    *,
    faiss_storage_type: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> float:
    local = prepare_faiss_workspace(
        index_folder,
        faiss_storage_type=faiss_storage_type,
        databricks_server_hostname=databricks_server_hostname,
        pull=True,
    )
    return _mtime_from_dir(local)


def load_cached_faiss_vectorstore(
    index_folder: str,
    embeddings: Any,
    *,
    faiss_storage_type: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> Any:
    """Load FAISS from disk once per path until the index folder mtime changes."""
    local = prepare_faiss_workspace(
        index_folder,
        faiss_storage_type=faiss_storage_type,
        databricks_server_hostname=databricks_server_hostname,
        pull=True,
    )
    mtime = _mtime_from_dir(local)
    cached = _cache.get(index_folder)
    if cached and cached[0] == mtime:
        return cached[1]

    vs = load_faiss_vectorstore(str(local), embeddings)
    _cache[index_folder] = (mtime, vs)
    logger.debug("faiss_cache_loaded", path=index_folder, local_path=str(local), mtime=mtime)
    return vs


def invalidate_faiss_cache(index_folder: Optional[str] = None) -> None:
    if index_folder:
        _cache.pop(index_folder, None)
    else:
        _cache.clear()


def append_to_faiss_index(
    index_folder: str,
    embeddings: Any,
    document: Document,
    *,
    faiss_storage_type: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> None:
    """Append one document to a FAISS index and invalidate the read cache."""
    from langchain_community.vectorstores import FAISS

    local = prepare_faiss_workspace(
        index_folder,
        faiss_storage_type=faiss_storage_type,
        databricks_server_hostname=databricks_server_hostname,
        pull=True,
    )
    index_file = local / "index.faiss"

    if index_file.exists():
        vs = load_faiss_vectorstore(str(local), embeddings)
        vs.add_documents([document])
    else:
        local.mkdir(parents=True, exist_ok=True)
        vs = FAISS.from_documents([document], embeddings)

    vs.save_local(str(local))
    finalize_faiss_workspace(
        index_folder,
        faiss_storage_type=faiss_storage_type,
        databricks_server_hostname=databricks_server_hostname,
    )
    invalidate_faiss_cache(index_folder)
    logger.info("faiss_index_appended", path=index_folder, local_path=str(local))
