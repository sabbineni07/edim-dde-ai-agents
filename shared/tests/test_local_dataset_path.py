"""Tests for local dataset path resolution."""

from pathlib import Path

from shared.services.local_dataset_service import resolve_dataset_local_path, resolve_fallback_path


def test_resolve_dataset_local_path_relative_to_project_root():
    sample = resolve_fallback_path()
    resolved = resolve_dataset_local_path("data/sample_job_metrics.csv")
    assert resolved is not None
    assert resolved.resolve() == sample.resolve()


def test_resolve_dataset_local_path_absolute():
    sample = resolve_fallback_path()
    resolved = resolve_dataset_local_path(str(sample))
    assert resolved is not None
    assert resolved.resolve() == sample.resolve()


def test_resolve_dataset_local_path_missing():
    assert resolve_dataset_local_path("data/does-not-exist.csv") is None
