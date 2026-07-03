"""Resolve FAISS index folder paths for local disk or Databricks Unity Catalog volumes."""

from __future__ import annotations

from typing import Any, Optional

FAISS_STORAGE_LOCAL = "local"
FAISS_STORAGE_DATABRICKS_VOLUME = "databricks_volume"

_VOLUME_PREFIX = "/Volumes/"


def normalize_faiss_storage_type(
    value: Optional[str],
    *,
    index_path: Optional[str] = None,
) -> str:
    """Return ``local`` or ``databricks_volume``."""
    raw = (value or "").strip().lower()
    if raw in ("volume", "databricks_volume", "uc_volume", "unity_catalog_volume"):
        return FAISS_STORAGE_DATABRICKS_VOLUME
    if raw == FAISS_STORAGE_LOCAL:
        return FAISS_STORAGE_LOCAL
    path = (index_path or "").strip()
    if path.startswith(_VOLUME_PREFIX):
        return FAISS_STORAGE_DATABRICKS_VOLUME
    return FAISS_STORAGE_LOCAL


def resolve_faiss_index_path(
    *,
    faiss_index_path: Optional[str],
    faiss_storage_type: Optional[str] = None,
) -> Optional[str]:
    """Return the filesystem path used by LangChain FAISS load/save helpers."""
    raw = (faiss_index_path or "").strip()
    if not raw:
        return None

    storage = normalize_faiss_storage_type(faiss_storage_type, index_path=raw)
    path = raw.rstrip("/")

    if storage == FAISS_STORAGE_DATABRICKS_VOLUME and not path.startswith(_VOLUME_PREFIX):
        raise ValueError(
            "Databricks Volume index path must start with /Volumes/<catalog>/<schema>/<volume>/…; "
            f"got: {raw!r}"
        )
    return path


def resolve_faiss_index_path_from_settings(settings: Any) -> Optional[str]:
    """Resolve index folder from a Settings instance or settings-like mapping."""
    if settings is None:
        return None
    path = getattr(settings, "faiss_index_path", None)
    storage = getattr(settings, "faiss_storage_type", None)
    if path is None and isinstance(settings, dict):
        path = settings.get("faiss_index_path")
        storage = settings.get("faiss_storage_type")
    return resolve_faiss_index_path(
        faiss_index_path=path,
        faiss_storage_type=storage,
    )
