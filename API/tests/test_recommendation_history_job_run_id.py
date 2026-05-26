"""Tests for job_run_id on recommendation history."""

from types import SimpleNamespace

from API.src.routes.jobs import _job_run_id_from_history


def test_job_run_id_from_history_column():
    rec = SimpleNamespace(job_run_id="run-001-001")
    assert _job_run_id_from_history(rec, None) == "run-001-001"


def test_job_run_id_from_request_log_params():
    rec = SimpleNamespace(job_run_id=None)
    req_log = SimpleNamespace(request_params={"job_run_id": "run-001-002", "job_id": "job-001"})
    assert _job_run_id_from_history(rec, req_log) == "run-001-002"


def test_job_run_id_prefers_column_over_request_log():
    rec = SimpleNamespace(job_run_id="run-001-003")
    req_log = SimpleNamespace(request_params={"job_run_id": "run-001-002"})
    assert _job_run_id_from_history(rec, req_log) == "run-001-003"
