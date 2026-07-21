"""Tests for Databricks collector schema-aware SQL."""

from DE.src.collectors.databricks_collector import DatabricksCollector


def test_job_run_id_select_when_column_present():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "cluster_id", "job_run_id"}
    assert collector._job_run_id_select() == "CAST(job_run_id AS STRING) AS job_run_id"
    assert (
        collector._job_run_id_select(aggregate_max=True)
        == "CAST(MAX(job_run_id) AS STRING) AS job_run_id"
    )


def test_job_run_id_select_when_column_missing():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "cluster_id"}
    assert collector._job_run_id_select() == "CAST(NULL AS STRING) AS job_run_id"
    assert collector._job_run_id_select(aggregate_max=True) == "CAST(NULL AS STRING) AS job_run_id"


def test_status_select_when_column_present():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "cluster_id", "status"}
    assert collector._status_select() == "CAST(status AS STRING) AS status"
    assert collector._status_select(aggregate_max=True) == "CAST(MAX(status) AS STRING) AS status"


def test_job_list_status_selects_when_column_present():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "status", "job_run_date"}
    last_status, failed_count = collector._job_list_status_selects()
    assert "max_by(status, job_run_date)" in last_status
    assert "failed_run_count" in failed_count
    assert "failed" in failed_count


def test_job_list_status_selects_when_column_missing():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "cluster_id"}
    last_status, failed_count = collector._job_list_status_selects()
    assert last_status == "CAST(NULL AS STRING) AS last_job_run_status"
    assert failed_count == "CAST(0 AS BIGINT) AS failed_run_count"


def test_metrics_select_includes_null_job_run_id_when_column_missing():
    collector = DatabricksCollector()
    collector._table_columns = {"job_id", "cluster_id"}
    sql = collector._metrics_select()
    assert "CAST(NULL AS STRING) AS job_run_id" in sql
    assert "job_run_id AS STRING" not in sql.replace("CAST(NULL AS STRING) AS job_run_id", "")
