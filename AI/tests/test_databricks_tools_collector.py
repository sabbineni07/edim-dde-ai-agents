"""Tests that agent tools honor request-scoped metrics collectors."""

from unittest.mock import MagicMock, patch

from AI.src.tools.databricks_tools import get_cost_analysis, get_job_cluster_metrics
from shared.factories.data_collector_context import reset_metrics_collector, set_metrics_collector


def test_get_cost_analysis_uses_scoped_collector():
    scoped = MagicMock()
    scoped.collect_cost_data.return_value = [{"job_id": "job-1", "total_cost_usd": 12.5}]
    token = set_metrics_collector(scoped)
    try:
        out = get_cost_analysis.invoke(
            {
                "job_id": "job-1",
                "start_date": "2024-01-15",
                "end_date": "2024-01-20",
            }
        )
        assert out["total_cost_usd"] == 12.5
        scoped.collect_cost_data.assert_called_once_with(
            start_date="2024-01-15",
            end_date="2024-01-20",
            job_ids=["job-1"],
        )
    finally:
        reset_metrics_collector(token)


def test_get_job_cluster_metrics_uses_scoped_collector():
    scoped = MagicMock()
    metric = MagicMock()
    metric.job_id = "job-1"
    metric.cluster_id = "cluster-abc"
    metric.job_run_id = "jr-1"
    metric.job_run_duration_seconds = 100.0
    scoped.collect_job_cluster_metrics.return_value = [metric]
    token = set_metrics_collector(scoped)
    try:
        with patch(
            "AI.src.tools.databricks_tools.select_job_run_metrics",
            return_value={
                "job_id": "job-1",
                "cluster_id": "cluster-abc",
                "job_run_id": "jr-1",
                "job_run_date": "2024-01-15",
                "avg_worker_nodes_consumed": 4.0,
                "p99_worker_nodes_consumed": 6.0,
                "azure_worker_vm_size": "Standard_E8s_v3",
                "max_worker_nodes_provisioned": 8,
                "avg_worker_cpu_utilization_pct": 50.0,
                "avg_worker_memory_utilization_pct": 60.0,
            },
        ):
            out = get_job_cluster_metrics.invoke(
                {
                    "job_id": "job-1",
                    "cluster_id": "cluster-abc",
                }
            )
        assert out["cluster_id"] == "cluster-abc"
        scoped.collect_job_cluster_metrics.assert_called_once()
    finally:
        reset_metrics_collector(token)
