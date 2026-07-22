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
    assert pack["sections"]["sql_plans"]["sql_errors"]
    assert pack["evidence"]
    assert any(e["source"] == "spark_logs" for e in pack["evidence"])


def test_build_evidence_pack_sql_plans_preserves_physical_plan():
    pack = build_evidence_pack(
        job_run_id="jr-2",
        failure_anchors=[
            {
                "event_id": "pe1",
                "event_type": "pipeline_end",
                "successful": False,
                "failure_reason": "Query failed",
                "attributes": {},
            }
        ],
        sql_plans=[
            {
                "event_id": "sql1",
                "event_type": "spark_sql_query_error",
                "successful": False,
                "failure_reason": "OOM during shuffle",
                "attributes": {
                    "error_type": "OutOfMemoryError",
                    "join_types": ["SortMergeJoin"],
                    "sql_text": "SELECT * FROM big_join",
                    "physical_plan": "Exchange hashpartitioning(id, 200)\n+- SortMergeJoin",
                },
            }
        ],
        stage_pressure=[
            {
                "event_id": "st1",
                "event_type": "spark_stage_completed",
                "status": "failed",
                "attributes": {
                    "num_failed_tasks": 2,
                    "memory_bytes_spilled": 999,
                    "status": "failed",
                },
            }
        ],
    )
    sql_err = pack["sections"]["sql_plans"]["sql_errors"][0]
    assert "physical_plan" in sql_err["attributes"]
    assert "SortMergeJoin" in sql_err["attributes"]["physical_plan"]
    assert "SELECT * FROM big_join" in sql_err["attributes"]["sql_text"]
    plan_evidence = [
        e for e in pack["evidence"] if "spark_sql_query_error" in str(e.get("ref") or "")
    ]
    assert plan_evidence
    assert "physical_plan=" in plan_evidence[0]["excerpt"]
    assert pack["sections"]["stage_metrics"]["stage_pressure_excerpts"]
    assert pack["raw_anchors"]["pipeline_end"] is not None


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


def test_validate_nested_recommendations_and_confidence_label():
    pack = build_evidence_pack(
        job_run_id="jr-1",
        failure_anchors=[
            {
                "event_id": "e1",
                "event_type": "pipeline_end",
                "successful": False,
                "failure_reason": "OOM",
                "attributes": {},
            }
        ],
    )
    validated = validate_rca_llm_output(
        {
            "job_status": "FAILED",
            "category": "Executor Out-of-Memory",
            "confidence_label": "High",
            "summary": "Executor OOM during shuffle.",
            "evidence_analysis": {
                "log_signals": "OutOfMemoryError on executor",
                "metric_anomalies": "high spill",
                "physical_plan_bottlenecks": "",
            },
            "recommendations": {
                "code_query_rewrites": ["Avoid wide collect"],
                "spark_delta_configs": ["SET spark.sql.shuffle.partitions = 200;"],
                "infrastructure": ["Increase executor memoryOverhead"],
            },
            "evidence_refs": [],
        },
        evidence_pack=pack,
        classification_hint={"category": "resource", "confidence": 0.5},
    )
    assert validated["root_cause"]["category"] == "resource"
    assert validated["root_cause"]["confidence"] >= 0.75
    assert validated["root_cause"]["confidence_label"] == "High"
    assert "Avoid wide collect" in validated["recommended_actions"]
    assert validated["recommendations"]["spark_delta_configs"]
    assert validated["evidence_analysis"]["log_signals"]
