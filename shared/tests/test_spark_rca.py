"""Unit tests for Spark RCA evidence pack and classification."""

from shared.rca.classify import classify_failure
from shared.rca.evidence_pack import build_evidence_pack
from shared.rca.validate import validate_rca_llm_output


def test_build_evidence_pack_includes_sql_error_refs():
    pack = build_evidence_pack(
        job_run_id="jr-1",
        job_id="j-1",
        failure_anchors=[
            {
                "event_id": "e1",
                "event_type": "spark_sql_query_error",
                "event_ts": "2026-07-18T10:00:00Z",
                "successful": False,
                "failure_reason": "Table not found: sales_raw",
                "attributes": {
                    "error_type": "AnalysisException",
                    "sql_text": "SELECT * FROM sales_raw",
                },
            }
        ],
        error_logs=[
            {
                "log_timestamp": "2026-07-18T10:00:01Z",
                "log_level": "ERROR",
                "message": "query failed",
                "exception": "AnalysisException: Table not found: sales_raw",
            }
        ],
        timeline=[],
        stage_pressure=[],
    )
    assert pack["raw_anchors"]["sql_errors"]
    assert pack["evidence"]
    assert any(e["source"] == "spark_logs" for e in pack["evidence"])


def test_classify_sql_error():
    pack = build_evidence_pack(
        job_run_id="jr-1",
        failure_anchors=[
            {
                "event_id": "e1",
                "event_type": "spark_sql_query_error",
                "successful": False,
                "failure_reason": "Table not found",
                "attributes": {"error_type": "AnalysisException"},
            }
        ],
    )
    hint = classify_failure(pack)
    assert hint["category"] == "sql_error"


def test_validate_falls_back_and_cites_evidence():
    pack = build_evidence_pack(
        job_run_id="jr-1",
        failure_anchors=[
            {
                "event_id": "e1",
                "event_type": "pipeline_end",
                "successful": False,
                "failure_reason": "OOM",
                "attributes": {"error_message": "Java heap space"},
            }
        ],
    )
    hint = classify_failure(pack)
    validated = validate_rca_llm_output(
        {"category": "not_a_real_category", "summary": "", "confidence": 2.5},
        evidence_pack=pack,
        classification_hint=hint,
    )
    assert validated["root_cause"]["category"] in (
        "resource",
        "unknown",
        "sql_error",
        "config",
        "data_quality",
        "skew_shuffle",
        "timeout_or_cancel",
    )
    assert 0.0 <= validated["root_cause"]["confidence"] <= 1.0
    assert validated["evidence"]
