"""Sync FAISS index files to/from Databricks Unity Catalog volumes via the Files API.

When ``faiss_storage_type`` is ``databricks_volume`` and the process is not running
inside a Databricks App with a mounted ``/Volumes/...`` path, index files are staged
under ``data/cache/faiss_volume/`` locally and uploaded/downloaded through
``WorkspaceClient.files`` (same workspace auth as SQL metrics collection).
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.rag.faiss_paths import (
    FAISS_STORAGE_DATABRICKS_VOLUME,
    FAISS_STORAGE_LOCAL,
    normalize_faiss_storage_type,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

FAISS_INDEX_FILENAMES = ("index.faiss", "index.pkl")


def is_databricks_app_runtime() -> bool:
    return bool(os.environ.get("DATABRICKS_APP_NAME"))


def volume_root_path(volume_path: str) -> str:
    """Return ``/Volumes/<catalog>/<schema>/<volume>`` from a volume URI."""
    parts = volume_path.rstrip("/").split("/")
    if len(parts) < 5 or parts[0] != "" or parts[1] != "Volumes":
        raise ValueError(
            "Databricks Volume path must start with /Volumes/<catalog>/<schema>/<volume>/…; "
            f"got: {volume_path!r}"
        )
    return "/".join(parts[:5])


def volume_mounted_locally(volume_path: str) -> bool:
    """True when the UC volume root exists on the local filesystem (Databricks Apps)."""
    try:
        return Path(volume_root_path(volume_path)).is_dir()
    except ValueError:
        return False


def uses_remote_volume_api(
    faiss_storage_type: Optional[str],
    index_path: str,
) -> bool:
    """True when FAISS should read/write the volume through the Databricks Files API."""
    storage = normalize_faiss_storage_type(faiss_storage_type, index_path=index_path)
    if storage != FAISS_STORAGE_DATABRICKS_VOLUME:
        return False
    if is_databricks_app_runtime() and volume_mounted_locally(index_path):
        return False
    return True


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _local_cache_dir(volume_path: str) -> Path:
    digest = hashlib.sha256(volume_path.encode("utf-8")).hexdigest()[:16]
    return _project_root() / "data" / "cache" / "faiss_volume" / digest


def _get_workspace_client(*, databricks_server_hostname: Optional[str] = None):
    from shared.databricks.workspace_client import (
        get_workspace_client,
        require_workspace_host_for_volume,
    )

    require_workspace_host_for_volume(databricks_server_hostname=databricks_server_hostname)
    return get_workspace_client(databricks_server_hostname=databricks_server_hostname)


def _parse_last_modified(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _remote_mtime(client: object, remote_path: str) -> Optional[float]:
    try:
        from databricks.sdk.errors import NotFound

        meta = client.files.get_metadata(remote_path)
    except NotFound:
        return None
    except Exception as e:
        logger.debug("faiss_volume_metadata_failed", path=remote_path, error=str(e))
        return None
    return _parse_last_modified(getattr(meta, "last_modified", None))


def _ensure_remote_directory(client: object, directory_path: str) -> None:
    try:
        from databricks.sdk.errors import AlreadyExists

        client.files.create_directory(directory_path.rstrip("/"))
    except AlreadyExists:
        pass
    except Exception as e:
        logger.debug("faiss_volume_mkdir", path=directory_path, error=str(e))


def pull_volume_index_to_cache(
    volume_path: str,
    *,
    databricks_server_hostname: Optional[str] = None,
) -> Path:
    """Download FAISS index files from a UC volume into the local staging directory."""
    cache_dir = _local_cache_dir(volume_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = _get_workspace_client(databricks_server_hostname=databricks_server_hostname)
    remote_prefix = volume_path.rstrip("/")

    for name in FAISS_INDEX_FILENAMES:
        remote = f"{remote_prefix}/{name}"
        local = cache_dir / name
        remote_mtime = _remote_mtime(client, remote)
        if remote_mtime is None:
            if local.is_file():
                local.unlink()
            continue
        if local.is_file() and local.stat().st_mtime >= remote_mtime - 1:
            continue
        client.files.download_to(remote, str(local), overwrite=True)
        logger.debug("faiss_volume_pulled", remote=remote, local=str(local))

    return cache_dir


def push_cache_to_volume(
    volume_path: str,
    *,
    databricks_server_hostname: Optional[str] = None,
) -> None:
    """Upload staged FAISS index files from the local cache to a UC volume."""
    cache_dir = _local_cache_dir(volume_path)
    if not cache_dir.is_dir():
        return

    client = _get_workspace_client(databricks_server_hostname=databricks_server_hostname)
    remote_prefix = volume_path.rstrip("/")
    _ensure_remote_directory(client, remote_prefix)

    for name in FAISS_INDEX_FILENAMES:
        local = cache_dir / name
        if not local.is_file():
            continue
        remote = f"{remote_prefix}/{name}"
        client.files.upload_from(remote, str(local), overwrite=True)
        logger.debug("faiss_volume_pushed", remote=remote)

    logger.info("faiss_volume_sync_complete", volume_path=remote_prefix)


def prepare_faiss_workspace(
    index_path: str,
    *,
    faiss_storage_type: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
    pull: bool = True,
) -> Path:
    """Return the local directory LangChain FAISS should read from or write to."""
    storage = normalize_faiss_storage_type(faiss_storage_type, index_path=index_path)
    if storage == FAISS_STORAGE_LOCAL:
        return Path(index_path)
    if uses_remote_volume_api(storage, index_path):
        if pull:
            return pull_volume_index_to_cache(
                index_path,
                databricks_server_hostname=databricks_server_hostname,
            )
        return _local_cache_dir(index_path)
    return Path(index_path)


def finalize_faiss_workspace(
    index_path: str,
    *,
    faiss_storage_type: Optional[str] = None,
    databricks_server_hostname: Optional[str] = None,
) -> None:
    """After ``save_local``, upload index files to the UC volume when using remote API."""
    storage = normalize_faiss_storage_type(faiss_storage_type, index_path=index_path)
    if storage == FAISS_STORAGE_LOCAL:
        return
    if uses_remote_volume_api(storage, index_path):
        push_cache_to_volume(
            index_path,
            databricks_server_hostname=databricks_server_hostname,
        )
