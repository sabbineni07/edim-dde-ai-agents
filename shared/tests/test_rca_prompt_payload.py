"""Tests for RCA human prompt payload formatting."""

from shared.rca.evidence_pack import build_evidence_pack
from shared.rca.prompt_payload import format_rca_human_payload


def test_format_rca_human_payload_sections():
    pack = build_evidence_pack(
        job_run_id="jr-1",
        job_id="j-1",
        workspace_id="ws-1",
        job_run_date="2026-07-18",
        task_key="main",
        failure_anchors=[
            {
                "event_id": "e1",
                "event_type": "spark_sql_query_error",
                "successful": False,
                "failure_reason": "Table not found",
                "attributes": {
                    "error_type": "AnalysisException",
                    "sql_text": "SELECT 1",
                    "physical_plan": "FileScan",
                },
            }
        ],
        error_logs=[
            {
                "log_timestamp": "2026-07-18T10:00:01Z",
                "log_level": "ERROR",
                "message": "boom",
                "exception": "AnalysisException: Table not found",
            }
        ],
        stage_pressure=[
            {
                "event_id": "s1",
                "event_type": "spark_stage_completed",
                "status": "failed",
                "attributes": {"num_failed_tasks": 3, "status": "failed"},
            }
        ],
        timeline=[
            {
                "event_ts": "2026-07-18T10:00:00Z",
                "event_type": "pipeline_start",
                "status": "running",
            }
        ],
    )
    payload = format_rca_human_payload(pack, classification_hint="category=sql_error")
    assert payload["workspace_id"] == "ws-1"
    assert payload["job_run_id"] == "jr-1"
    assert "AnalysisException" in payload["cluster_logs_section"]
    assert (
        "spark_stage_completed" in payload["spark_metrics_section"]
        or "failed" in payload["spark_metrics_section"]
    )
    assert (
        "sql_text" in payload["query_plans_section"] or "FileScan" in payload["query_plans_section"]
    )
    assert '"job_run_id": "jr-1"' in payload["evidence_pack"]
    assert '"sql_errors"' in payload["query_plans_section"]
    assert "top_exceptions" in payload["cluster_logs_section"]
