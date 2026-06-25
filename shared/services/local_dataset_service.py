"""User-scoped local file storage — generic; validation is use-case specific."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

UploadValidator = Callable[[bytes], tuple[Optional[int], list[str]]]

_META_FILENAME = "dataset_meta.json"
_DEFAULT_DATASET_KEY = "default"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _uploads_root() -> Path:
    return _project_root() / "data" / "uploads"


def _sanitize_user_id(user_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", (user_id or "anonymous").strip())[:128]
    return cleaned or "anonymous"


def _sanitize_dataset_key(dataset_key: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", (dataset_key or _DEFAULT_DATASET_KEY).strip())[:64]
    return cleaned or _DEFAULT_DATASET_KEY


def _user_dataset_dir(user_id: str, dataset_key: str) -> Path:
    return _uploads_root() / _sanitize_user_id(user_id) / _sanitize_dataset_key(dataset_key)


def _meta_path(user_id: str, dataset_key: str) -> Path:
    return _user_dataset_dir(user_id, dataset_key) / _META_FILENAME


def _upload_path(user_id: str, dataset_key: str, filename: str) -> Path:
    return _user_dataset_dir(user_id, dataset_key) / filename


def resolve_fallback_path(fallback_path: Optional[str] = None) -> Path:
    if fallback_path:
        p = Path(fallback_path)
        return p if p.is_absolute() else _project_root() / p
    if settings.local_data_path:
        p = Path(settings.local_data_path)
        return p if p.is_absolute() else _project_root() / p
    return _project_root() / "data" / "sample_job_metrics.csv"


def get_active_file_path(
    user_id: str,
    *,
    dataset_key: str = _DEFAULT_DATASET_KEY,
    stored_filename: str = "dataset.csv",
    fallback_path: Optional[str] = None,
) -> Path:
    """Uploaded file for user/dataset, else fallback path."""
    uploaded = _upload_path(user_id, dataset_key, stored_filename)
    if uploaded.is_file():
        return uploaded
    return resolve_fallback_path(fallback_path)


def get_dataset_info(
    user_id: str,
    *,
    dataset_key: str = _DEFAULT_DATASET_KEY,
    stored_filename: str = "dataset.csv",
    fallback_path: Optional[str] = None,
) -> Dict[str, Any]:
    uploaded = _upload_path(user_id, dataset_key, stored_filename)
    meta_file = _meta_path(user_id, dataset_key)
    meta: Dict[str, Any] = {}
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    if uploaded.is_file():
        stat = uploaded.stat()
        return {
            "source": "upload",
            "filename": meta.get("original_filename") or stored_filename,
            "uploaded_at": meta.get("uploaded_at"),
            "row_count": meta.get("row_count"),
            "file_size_bytes": stat.st_size,
            "using_sample": False,
            "dataset_key": _sanitize_dataset_key(dataset_key),
        }

    sample = resolve_fallback_path(fallback_path)
    return {
        "source": "sample",
        "filename": sample.name,
        "uploaded_at": None,
        "row_count": None,
        "file_size_bytes": sample.stat().st_size if sample.is_file() else None,
        "using_sample": True,
        "dataset_key": _sanitize_dataset_key(dataset_key),
    }


def save_upload(
    user_id: str,
    original_filename: str,
    content: bytes,
    *,
    dataset_key: str = _DEFAULT_DATASET_KEY,
    stored_filename: str = "dataset.csv",
    validator: Optional[UploadValidator] = None,
) -> Dict[str, Any]:
    row_count: Optional[int] = None
    if validator:
        row_count, errors = validator(content)
        if errors:
            raise ValueError("; ".join(errors))

    dest = _upload_path(user_id, dataset_key, stored_filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    meta = {
        "original_filename": original_filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "row_count": row_count,
        "stored_filename": stored_filename,
    }
    _meta_path(user_id, dataset_key).write_text(json.dumps(meta, indent=2), encoding="utf-8")

    logger.info(
        "local_dataset_saved",
        user_id=_sanitize_user_id(user_id),
        dataset_key=_sanitize_dataset_key(dataset_key),
        row_count=row_count,
        path=str(dest),
    )
    return get_dataset_info(
        user_id,
        dataset_key=dataset_key,
        stored_filename=stored_filename,
    )


def clear_upload(
    user_id: str,
    *,
    dataset_key: str = _DEFAULT_DATASET_KEY,
    stored_filename: str = "dataset.csv",
    fallback_path: Optional[str] = None,
) -> Dict[str, Any]:
    uploaded = _upload_path(user_id, dataset_key, stored_filename)
    meta = _meta_path(user_id, dataset_key)
    if uploaded.is_file():
        uploaded.unlink()
    if meta.is_file():
        meta.unlink()
    logger.info(
        "local_dataset_cleared",
        user_id=_sanitize_user_id(user_id),
        dataset_key=_sanitize_dataset_key(dataset_key),
    )
    return get_dataset_info(
        user_id,
        dataset_key=dataset_key,
        stored_filename=stored_filename,
        fallback_path=fallback_path,
    )
