"""Tests for job run ingest mapping."""

from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.models.job_run_ingest import to_llm_ingest_dict
from shared.sizing.policy import (
    compute_sizing_hints,
    infer_reason_codes,
    recommended_min_max_workers,
)


def _sample_metrics() -> JobClusterMetrics:
    return JobClusterMetrics(
        date="2026-04-30",
        workspace_id="ws-1",
        job_id="job-1",
        job_run_id="run-99",
        job_duration_seconds=1540.0,
        task_count=10,
        parallelism_ratio=2.0,
        avg_cpu_utilization_pct=4.48,
        avg_memory_utilization_pct=10.0,
        peak_cpu_utilization_pct=25.0,
        peak_memory_utilization_pct=30.0,
        avg_nodes_consumed=2.0,
        p95_nodes_consumed=6.0,
        p99_nodes_consumed=8.0,
        total_cost_usd=1.0,
        cost_per_hour_usd=0.1,
        current_node_type="Standard_E8s_v3",
        current_min_workers=1,
        current_max_workers=17,
        job_date="2026-04-30",
    )


def test_to_llm_ingest_dict_copilot_field_names():
    ingest = to_llm_ingest_dict(_sample_metrics())
    assert ingest["job_run_id"] == "run-99"
    assert ingest["workflow_task_count"] == 10
    assert ingest["azure_worker_vm_size"] == "Standard_E8s_v3"
    assert ingest["max_worker_nodes_cluster_ceiling"] == 17
    assert ingest["avg_worker_nodes_consumed"] == 2.0
    assert "avg_vcpus_allocated_active_cluster" in ingest
    assert "avg_vcpus_utilized_by_workload" in ingest


def test_sizing_hints_and_reason_codes():
    ingest = to_llm_ingest_dict(_sample_metrics())
    hints = compute_sizing_hints(ingest)
    assert hints["recommended_max_workers"] >= 1
    codes = infer_reason_codes(ingest, {"node_family": "E", "max_workers": 4}, change_required=True)
    assert len(codes) >= 1
    assert "OVERPROVISIONED_AUTOSCALE" in codes or "PER_NODE_UNDERUTILIZED" in codes


def test_auto_termination_always_immediate():
    from shared.guardrails.output_guardrails import validate_and_clamp_recommendation

    out = validate_and_clamp_recommendation(
        {
            "node_family": "E",
            "vcpus": 8,
            "min_workers": 1,
            "max_workers": 8,
            "auto_termination_minutes": 20,
            "rationale": "test",
        }
    )
    assert out["auto_termination_minutes"] == 0


def test_recommended_min_max_workers_from_nodes_not_task_count():
    ingest = to_llm_ingest_dict(_sample_metrics())
    _, max_w = recommended_min_max_workers(ingest)
    # p95=6, 10% buffer -> ceil(6.6)=7; must not use workflow_task_count=150
    assert max_w == 7


def test_guardrail_syncs_rationale_max_workers():
    from shared.guardrails.output_guardrails import validate_and_clamp_recommendation

    ingest = to_llm_ingest_dict(_sample_metrics())
    out = validate_and_clamp_recommendation(
        {
            "node_family": "E",
            "vcpus": 8,
            "min_workers": 1,
            "max_workers": 8,
            "auto_termination_minutes": 20,
            "rationale": "Recommend max_workers of 8 based on p99 nodes.",
        },
        job_run_ingest=ingest,
    )
    assert out["max_workers"] == 8  # LLM value >= floor (7); not raised
    assert "max_workers=8" in out["rationale"]
    assert "auto_termination_minutes=0" in out["rationale"]
