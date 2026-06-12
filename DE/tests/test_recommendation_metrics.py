"""Tests for recommendation metrics resolver."""

from unittest.mock import MagicMock, patch

from DE.src.access import recommendation_metrics as mod
from DE.src.access.recommendation_metrics import fetch_job_run_metrics_for_recommendation


def test_fetch_by_cluster_id_without_dates():
    mock_collector = MagicMock()
    mock_metric = MagicMock()
    mock_metric.job_id = "job-1"
    mock_metric.cluster_id = "cluster-abc"
    mock_metric.job_run_id = "jr-1"
    mock_metric.job_run_duration_seconds = 100.0
    mock_collector.collect_job_cluster_metrics.return_value = [mock_metric]

    with patch.object(mod, "_resolve_collector", return_value=mock_collector):
        with patch.object(
            mod,
            "select_job_run_metrics",
            return_value={
                "job_id": "job-1",
                "cluster_id": "cluster-abc",
                "job_run_id": "jr-1",
                "job_run_date": "2026-06-01",
                "avg_worker_nodes_consumed": 4.0,
                "p99_worker_nodes_consumed": 6.0,
                "azure_worker_vm_size": "Standard_E8s_v3",
                "max_worker_nodes_provisioned": 8,
                "avg_worker_cpu_utilization_pct": 50.0,
                "avg_worker_memory_utilization_pct": 60.0,
            },
        ):
            out = fetch_job_run_metrics_for_recommendation(
                environment_id="dim_dev",
                user_id="user-1",
                connection_id="conn-1",
                job_id="job-1",
                cluster_id="cluster-abc",
            )

    assert out is not None
    assert out["cluster_id"] == "cluster-abc"
    assert out["job_run_id"] == "jr-1"
    mock_collector.collect_job_cluster_metrics.assert_called_once_with(
        start_date=None,
        end_date=None,
        job_ids=["job-1"],
        cluster_id="cluster-abc",
        job_run_id=None,
    )
