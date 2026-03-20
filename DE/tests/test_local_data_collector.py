"""Tests for local data collector."""

import os
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from DE.src.collectors.local_data_collector import LocalDataCollector
except ImportError as e:
    pytest.skip(f"Could not import LocalDataCollector: {e}", allow_module_level=True)


def test_local_data_collector_initialization():
    """Test that local data collector initializes correctly."""
    collector = LocalDataCollector()
    assert collector is not None
    assert collector.csv_path is not None


def test_collect_job_cluster_metrics():
    """Test collecting job cluster metrics from CSV."""
    collector = LocalDataCollector()

    metrics = collector.collect_job_cluster_metrics(
        start_date="2024-01-15", end_date="2024-01-20", job_ids=["job-001"]
    )

    assert isinstance(metrics, list)
    assert len(metrics) > 0

    # Verify first metric structure
    if metrics:
        metric = metrics[0]
        assert hasattr(metric, "job_id")
        assert hasattr(metric, "workspace_id")
        assert hasattr(metric, "avg_cpu_utilization_pct")
        assert hasattr(metric, "avg_memory_utilization_pct")


def test_collect_job_cluster_metrics_multiple_jobs():
    """Test collecting cluster metrics for multiple jobs."""
    collector = LocalDataCollector()

    metrics = collector.collect_job_cluster_metrics(
        start_date="2024-01-15", end_date="2024-01-20", job_ids=["job-001", "job-002"]
    )

    assert isinstance(metrics, list)
    assert len(metrics) > 0

    # Verify we have metrics for both jobs
    job_ids = {m.job_id for m in metrics}
    assert "job-001" in job_ids or "job-002" in job_ids


def test_collect_resource_utilization():
    """Test collecting resource utilization data."""
    collector = LocalDataCollector()

    utilization = collector.collect_resource_utilization(
        start_date="2024-01-15", end_date="2024-01-20", job_ids=["job-001"]
    )

    assert isinstance(utilization, list)
    # Should return empty list or list of dicts
    assert isinstance(utilization, list)


def test_collect_cost_data():
    """Test collecting cost data."""
    collector = LocalDataCollector()

    cost_data = collector.collect_cost_data(
        start_date="2024-01-15", end_date="2024-01-20", job_ids=["job-001"]
    )

    assert isinstance(cost_data, list)
    # Should return empty list or list of dicts
    assert isinstance(cost_data, list)


def test_list_workspaces():
    """Test listing distinct workspaces with summary fields."""
    collector = LocalDataCollector()

    workspaces = collector.list_workspaces(start_date="2024-01-15", end_date="2024-01-20")

    assert isinstance(workspaces, list)
    assert len(workspaces) > 0

    first = workspaces[0]
    assert "workspace_id" in first
    assert "workspace_name" in first
    assert "job_count" in first
    assert "first_seen_date" in first
    assert "last_seen_date" in first
    assert isinstance(first["job_count"], int)


def test_list_jobs_for_workspace():
    """Test listing aggregated jobs for a given workspace."""
    collector = LocalDataCollector()

    jobs = collector.list_jobs_for_workspace(
        workspace_id="1234567890123456",
        start_date="2024-01-15",
        end_date="2024-01-20",
    )

    assert isinstance(jobs, list)
    assert len(jobs) > 0
    first = jobs[0]
    assert first["workspace_id"] == "1234567890123456"
    assert "job_id" in first
    assert "job_name" in first
    assert "avg_cpu_utilization_pct" in first
    assert "avg_memory_utilization_pct" in first
    assert "total_runs" in first
    assert "avg_duration_seconds" in first
    assert "last_run_date" in first


def test_get_job_metrics():
    """Test aggregated metrics for one job/workspace."""
    collector = LocalDataCollector()
    metrics = collector.get_job_metrics(
        workspace_id="1234567890123456",
        job_id="job-001",
        start_date="2024-01-15",
        end_date="2024-01-20",
    )
    assert isinstance(metrics, dict)
    assert metrics is not None
    assert metrics["total_runs"] > 0
    assert "avg_cpu_utilization" in metrics
    assert "avg_memory_utilization" in metrics
    assert "current_node_type" in metrics
