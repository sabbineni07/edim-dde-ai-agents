"""Tests for Databricks Volume FAISS staging and sync."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.rag.faiss_volume_storage import (
    FAISS_INDEX_FILENAMES,
    prepare_faiss_workspace,
    pull_volume_index_to_cache,
    push_cache_to_volume,
    uses_remote_volume_api,
    volume_root_path,
)


def test_volume_root_path():
    assert volume_root_path("/Volumes/cat/schema/vol/sub/index") == "/Volumes/cat/schema/vol"


def test_volume_root_path_invalid():
    with pytest.raises(ValueError, match="/Volumes/"):
        volume_root_path("/tmp/index")


def test_uses_remote_volume_api_local_storage():
    assert not uses_remote_volume_api("local", "/app/data/faiss_index")


def test_uses_remote_volume_api_volume_on_laptop():
    with patch(
        "shared.rag.faiss_volume_storage.is_databricks_app_runtime",
        return_value=False,
    ):
        assert uses_remote_volume_api(
            "databricks_volume",
            "/Volumes/cat/schema/vol/faiss_index",
        )


def test_uses_remote_volume_api_volume_on_mounted_app():
    with patch(
        "shared.rag.faiss_volume_storage.is_databricks_app_runtime",
        return_value=True,
    ):
        with patch(
            "shared.rag.faiss_volume_storage.volume_mounted_locally",
            return_value=True,
        ):
            assert not uses_remote_volume_api(
                "databricks_volume",
                "/Volumes/cat/schema/vol/faiss_index",
            )


def test_prepare_faiss_workspace_local_path():
    path = prepare_faiss_workspace("/tmp/faiss", faiss_storage_type="local", pull=False)
    assert path == Path("/tmp/faiss")


def test_prepare_faiss_workspace_remote_pulls_to_cache(tmp_path, monkeypatch):
    volume_path = "/Volumes/cat/schema/vol/faiss_index"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        "shared.rag.faiss_volume_storage._local_cache_dir",
        lambda _path: cache_dir,
    )
    with patch(
        "shared.rag.faiss_volume_storage.uses_remote_volume_api",
        return_value=True,
    ):
        with patch(
            "shared.rag.faiss_volume_storage.pull_volume_index_to_cache",
            return_value=cache_dir,
        ) as pull:
            result = prepare_faiss_workspace(
                volume_path,
                faiss_storage_type="databricks_volume",
                pull=True,
            )
            pull.assert_called_once_with(
                volume_path,
                databricks_server_hostname=None,
            )
            assert result == cache_dir


def test_pull_volume_index_to_cache_downloads_files(tmp_path, monkeypatch):
    volume_path = "/Volumes/cat/schema/vol/faiss_index"
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        "shared.rag.faiss_volume_storage._local_cache_dir",
        lambda _path: cache_dir,
    )

    client = MagicMock()
    client.files.get_metadata.side_effect = [
        MagicMock(last_modified="2026-01-01T00:00:00Z"),
        MagicMock(last_modified="2026-01-01T00:00:00Z"),
    ]

    with patch(
        "shared.rag.faiss_volume_storage._get_workspace_client",
        return_value=client,
    ) as get_client:
        result = pull_volume_index_to_cache(
            volume_path,
            databricks_server_hostname="adb.example.net",
        )

    get_client.assert_called_once_with(databricks_server_hostname="adb.example.net")

    assert result == cache_dir
    assert client.files.download_to.call_count == len(FAISS_INDEX_FILENAMES)


def test_push_cache_to_volume_uploads_existing_files(tmp_path, monkeypatch):
    volume_path = "/Volumes/cat/schema/vol/faiss_index"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for name in FAISS_INDEX_FILENAMES:
        (cache_dir / name).write_bytes(b"data")

    monkeypatch.setattr(
        "shared.rag.faiss_volume_storage._local_cache_dir",
        lambda _path: cache_dir,
    )

    client = MagicMock()
    with patch(
        "shared.rag.faiss_volume_storage._get_workspace_client",
        return_value=client,
    ):
        push_cache_to_volume(volume_path)

    assert client.files.create_directory.called
    assert client.files.upload_from.call_count == len(FAISS_INDEX_FILENAMES)
