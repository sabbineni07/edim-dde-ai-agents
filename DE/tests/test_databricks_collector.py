"""Tests for Databricks collector."""

from __future__ import annotations

from typing import Any, List, Optional

import pytest

from DE.src.collectors.databricks_collector import DatabricksCollector


class _FakeCursor:
    def __init__(
        self,
        *,
        description: List[tuple[str]],
        rows: Optional[List[tuple[Any, ...]]] = None,
        row: Optional[tuple[Any, ...]] = None,
    ):
        self.description = description
        self._rows = rows or []
        self._row = row
        self.executed_query = ""
        self.executed_params: List[Any] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params: List[Any]):
        self.executed_query = query
        self.executed_params = params

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


def _build_collector() -> DatabricksCollector:
    collector = object.__new__(DatabricksCollector)
    collector._metrics_table = "catalog.schema.metrics"
    collector._server_hostname = "adb.example.net"
    collector._http_path = "/sql/1.0/warehouses/abc"
    collector._table_columns = {"job_run_id"}
    collector._connection_params = lambda: {}
    return collector


def test_list_jobs_for_workspace_preserves_missing_worker_vm(monkeypatch):
    collector = _build_collector()
    cursor = _FakeCursor(
        description=[
            ("job_id",),
            ("job_name",),
            ("job_type",),
            ("avg_worker_cpu_utilization_pct",),
            ("avg_worker_memory_utilization_pct",),
            ("avg_driver_cpu_utilization_pct",),
            ("avg_driver_memory_utilization_pct",),
            ("total_runs",),
            ("avg_job_run_duration_seconds",),
            ("azure_driver_vm_size",),
            ("azure_worker_vm_size",),
            ("max_worker_nodes_provisioned",),
            ("cluster_type",),
            ("last_job_run_date",),
            ("last_job_run_status",),
            ("failed_run_count",),
            ("dbr_version",),
        ],
        rows=[
            (
                "job-1",
                "Single node job",
                "ETL",
                None,
                None,
                42.5,
                55.0,
                3,
                120.0,
                "Standard_DS3_v2",
                None,
                1,
                "single_node",
                "2026-07-01",
                "SUCCEEDED",
                0,
                "14.3.x-scala2.12",
            )
        ],
    )
    monkeypatch.setattr(
        "DE.src.collectors.databricks_collector.sql.connect",
        lambda **_kwargs: _FakeConnection(cursor),
    )

    rows = collector.list_jobs_for_workspace("ws-1", "2026-07-01", "2026-07-07")

    assert rows[0]["azure_driver_vm_size"] == "Standard_DS3_v2"
    assert rows[0]["azure_worker_vm_size"] is None
    assert rows[0]["avg_worker_cpu_utilization_pct"] is None
    assert rows[0]["avg_driver_cpu_utilization_pct"] == 42.5
    assert rows[0]["cluster_type"] == "single_node"
    assert "Standard_E8s_v3" not in cursor.executed_query


def test_list_job_runs_preserves_missing_worker_fields(monkeypatch):
    collector = _build_collector()
    cursor = _FakeCursor(
        description=[
            ("cluster_id",),
            ("job_run_id",),
            ("job_run_date",),
            ("job_run_duration_seconds",),
            ("azure_driver_vm_size",),
            ("driver_node_count",),
            ("avg_driver_cpu_utilization_pct",),
            ("avg_driver_memory_utilization_pct",),
            ("peak_driver_cpu_utilization_pct",),
            ("avg_worker_cpu_utilization_pct",),
            ("avg_worker_memory_utilization_pct",),
            ("avg_worker_nodes_consumed",),
            ("total_worker_vcpus_provisioned",),
            ("total_worker_memory_gb_provisioned",),
            ("peak_worker_cpu_utilization_pct",),
            ("peak_worker_memory_utilization_pct",),
            ("azure_worker_vm_size",),
            ("max_worker_nodes_provisioned",),
            ("job_type",),
            ("dbr_version",),
        ],
        rows=[
            (
                "cluster-1",
                "run-1",
                "2026-07-01",
                300.0,
                "Standard_DS3_v2",
                1,
                65.0,
                72.0,
                88.0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                1,
                "ETL",
                "14.3.x-scala2.12",
            )
        ],
    )
    monkeypatch.setattr(
        "DE.src.collectors.databricks_collector.sql.connect",
        lambda **_kwargs: _FakeConnection(cursor),
    )

    rows = collector.list_job_runs("ws-1", "job-1", "2026-07-01", "2026-07-07")

    assert rows[0]["azure_driver_vm_size"] == "Standard_DS3_v2"
    assert rows[0]["azure_worker_vm_size"] is None
    assert rows[0]["avg_worker_cpu_utilization_pct"] is None
    assert rows[0]["avg_worker_nodes_consumed"] is None
    assert "Standard_E8s_v3" not in cursor.executed_query


def test_get_job_metrics_preserves_missing_worker_fields(monkeypatch):
    collector = _build_collector()
    cursor = _FakeCursor(
        description=[
            ("avg_job_run_duration_seconds",),
            ("azure_driver_vm_size",),
            ("driver_node_count",),
            ("avg_driver_cpu_utilization_pct",),
            ("avg_driver_memory_utilization_pct",),
            ("peak_driver_cpu_utilization_pct",),
            ("avg_driver_vcpus_consumed",),
            ("avg_driver_memory_gb_consumed",),
            ("avg_worker_cpu_utilization_pct",),
            ("avg_worker_memory_utilization_pct",),
            ("peak_worker_cpu_utilization_pct",),
            ("peak_worker_memory_utilization_pct",),
            ("avg_worker_nodes_consumed",),
            ("p95_worker_nodes_consumed",),
            ("avg_total_worker_vcpus_provisioned",),
            ("avg_total_worker_memory_gb_provisioned",),
            ("p99_worker_nodes_consumed",),
            ("total_runs",),
            ("azure_worker_vm_size",),
            ("max_worker_nodes_provisioned",),
            ("last_job_run_date",),
            ("job_name",),
            ("dbr_version",),
            ("workspace_name",),
            ("job_run_start_time_utc",),
            ("job_run_end_time_utc",),
            ("delta_tables_ingested",),
            ("worker_node_provisioning_efficiency_pct",),
            ("worker_cpu_utilization_efficiency_pct",),
            ("worker_memory_utilization_efficiency_pct",),
            ("job_type",),
            ("processed_row_count",),
            ("processed_bytes",),
        ],
        row=(
            180.0,
            "Standard_DS3_v2",
            1,
            55.0,
            61.0,
            84.0,
            4.0,
            16.0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            4,
            None,
            1,
            "2026-07-01",
            "Single node job",
            "14.3.x-scala2.12",
            "Workspace 1",
            "2026-07-01T00:00:00Z",
            "2026-07-01T00:03:00Z",
            None,
            None,
            None,
            None,
            "ETL",
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "DE.src.collectors.databricks_collector.sql.connect",
        lambda **_kwargs: _FakeConnection(cursor),
    )

    row = collector.get_job_metrics("ws-1", "job-1", "2026-07-01", "2026-07-07")

    assert row is not None
    assert row["azure_driver_vm_size"] == "Standard_DS3_v2"
    assert row["azure_worker_vm_size"] is None
    assert row["avg_worker_cpu_utilization_pct"] is None
    assert row["p95_worker_nodes_consumed"] is None
    assert "Standard_E8s_v3" not in cursor.executed_query


@pytest.mark.skip(reason="Requires Databricks connection")
def test_collect_job_cluster_metrics():
    """Test job cluster metrics collection."""
    collector = DatabricksCollector()
    metrics = collector.collect_job_cluster_metrics(
        start_date="2024-01-01", end_date="2024-01-31", job_ids=["test-job-123"]
    )
    assert isinstance(metrics, list)
