"""Tests for recommendation pipeline (hints, guardrails, retry policy, merged sizing)."""

from AI.src.agents.dbx_cluster_tuning_agent.chains.sizing import (
    SIZING_LLM_RESPONSE_KEYS,
    split_sizing_llm_response,
)
from shared.guardrails.output_guardrails import validate_and_clamp_with_adjustments
from shared.guardrails.retry_policy import (
    build_guardrail_feedback,
    should_retry_cost_recommendation,
)
from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.models.job_run_ingest import to_llm_ingest_dict
from shared.sizing.policy import compute_sizing_hints, sizing_hints_for_llm


def _sample_metrics() -> JobClusterMetrics:
    return JobClusterMetrics(
        job_run_date="2026-04-30",
        workspace_id="ws-1",
        cluster_id="run-99",
        job_id="job-1",
        job_run_duration_seconds=1540.0,
        avg_worker_cpu_utilization_pct=4.48,
        avg_worker_memory_utilization_pct=10.0,
        peak_worker_cpu_utilization_pct=25.0,
        peak_worker_memory_utilization_pct=30.0,
        avg_worker_nodes_consumed=6.0,
        p99_worker_nodes_consumed=8.0,
        azure_worker_vm_size="Standard_E8s_v3",
        max_worker_nodes_provisioned=17,
    )


def test_sizing_hints_for_llm_omits_interpretive_fields():
    ingest = to_llm_ingest_dict(_sample_metrics())
    full = compute_sizing_hints(ingest)
    narrow = sizing_hints_for_llm(full)
    assert "recommended_max_workers" in narrow
    assert "suggested_vm_family" not in narrow
    assert "overprovisioned_autoscale" not in narrow


def test_guardrail_adjustments_sizing_floor():
    ingest = to_llm_ingest_dict(_sample_metrics())
    applied, adjustments = validate_and_clamp_with_adjustments(
        {
            "node_family": "E",
            "vcpus": 8,
            "min_workers": 1,
            "max_workers": 5,
            "auto_termination_minutes": 20,
            "rationale": "test",
        },
        job_run_ingest=ingest,
    )
    assert applied["max_workers"] == 7
    reasons = {a["reason"] for a in adjustments}
    assert "sizing_floor" in reasons
    assert "auto_termination_policy" in reasons


def test_should_retry_on_sizing_floor():
    adjustments = [
        {
            "field": "max_workers",
            "llm_value": 5,
            "applied_value": 7,
            "reason": "sizing_floor",
        }
    ]
    assert should_retry_cost_recommendation(adjustments, attempt=1, max_attempts=2)
    assert not should_retry_cost_recommendation(adjustments, attempt=2, max_attempts=2)


def test_should_not_retry_on_auto_termination_only():
    adjustments = [
        {
            "field": "auto_termination_minutes",
            "llm_value": 20,
            "applied_value": 0,
            "reason": "auto_termination_policy",
        }
    ]
    assert not should_retry_cost_recommendation(adjustments, attempt=1, max_attempts=2)


def test_split_sizing_llm_response():
    payload = {
        "pattern_analysis": "### 1. Workload type\n- ETL",
        "node_family": "E",
        "vcpus": 8,
        "min_workers": 0,
        "max_workers": 7,
        "auto_termination_minutes": 0,
        "rationale": "Sized from p95.",
    }
    pattern, rec = split_sizing_llm_response(payload)
    assert "Workload type" in pattern
    assert set(rec.keys()) == set(k for k in SIZING_LLM_RESPONSE_KEYS if k != "pattern_analysis")


def test_build_guardrail_feedback_includes_violations():
    adjustments = [
        {
            "field": "max_workers",
            "llm_value": 5,
            "applied_value": 7,
            "reason": "sizing_floor",
        },
        {
            "field": "auto_termination_minutes",
            "llm_value": 20,
            "applied_value": 0,
            "reason": "auto_termination_policy",
        },
    ]
    fb = build_guardrail_feedback(adjustments, attempt=2)
    assert fb["attempt"] == 2
    assert len(fb["violations"]) == 1
    assert fb["violations"][0]["field"] == "max_workers"
