"""Tests for FAISS index path resolution."""

import pytest

from shared.config.connection_types import validate_connection_config
from shared.rag.faiss_paths import (
    FAISS_STORAGE_DATABRICKS_VOLUME,
    FAISS_STORAGE_LOCAL,
    normalize_faiss_storage_type,
    resolve_faiss_index_path,
    resolve_faiss_index_path_from_settings,
)


def test_resolve_local_path():
    path = resolve_faiss_index_path(
        faiss_index_path="/app/data/faiss_index",
        faiss_storage_type="local",
    )
    assert path == "/app/data/faiss_index"


def test_resolve_volume_path():
    path = resolve_faiss_index_path(
        faiss_index_path="/Volumes/catalog/schema/volume/faiss_index",
        faiss_storage_type="databricks_volume",
    )
    assert path == "/Volumes/catalog/schema/volume/faiss_index"


def test_volume_storage_requires_volumes_prefix():
    with pytest.raises(ValueError, match="/Volumes/"):
        resolve_faiss_index_path(
            faiss_index_path="/app/data/faiss_index",
            faiss_storage_type="databricks_volume",
        )


def test_auto_detect_volume_from_path():
    assert (
        normalize_faiss_storage_type(None, index_path="/Volumes/c/s/v/index")
        == FAISS_STORAGE_DATABRICKS_VOLUME
    )
    assert normalize_faiss_storage_type(None, index_path="/tmp/index") == FAISS_STORAGE_LOCAL


def test_validate_faiss_connection_config_volume():
    clean = validate_connection_config(
        "faiss",
        {
            "faiss_storage_type": "databricks_volume",
            "faiss_index_path": "/Volumes/prod/rag/knowledge/faiss_index",
        },
    )
    assert clean["faiss_storage_type"] == FAISS_STORAGE_DATABRICKS_VOLUME


def test_resolve_from_settings_object():
    class _Cfg:
        faiss_index_path = "/Volumes/c/s/v/index"
        faiss_storage_type = "databricks_volume"

    assert resolve_faiss_index_path_from_settings(_Cfg()) == "/Volumes/c/s/v/index"
