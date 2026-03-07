"""Tests for Databricks collector."""
import pytest
from DE.src.collectors.databricks_collector import DatabricksCollector


@pytest.mark.skip(reason="Requires Databricks connection")
def test_collect_job_cluster_metrics():
    """Test job cluster metrics collection."""
    collector = DatabricksCollector()
    metrics = collector.collect_job_cluster_metrics(
        start_date="2024-01-01",
        end_date="2024-01-31",
        job_ids=["test-job-123"]
    )
    assert isinstance(metrics, list)

