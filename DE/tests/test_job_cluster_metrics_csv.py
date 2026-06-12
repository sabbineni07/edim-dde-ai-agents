"""Tests for job cluster metrics CSV schema."""

from DE.src.datasets.job_cluster_metrics_csv import REQUIRED_COLUMNS, validate_columns


def test_validate_columns_ok():
    assert validate_columns(list(REQUIRED_COLUMNS)) == []


def test_validate_columns_missing():
    errors = validate_columns(["job_run_date", "workspace_id"])
    assert len(errors) == 1
    assert "cluster_id" in errors[0] or "job_id" in errors[0]
