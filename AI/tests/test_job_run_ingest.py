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


def test_to_llm_ingest_dict_copilot_field_names():
    ingest = to_llm_ingest_dict(_sample_metrics())
    assert ingest["cluster_id"] == "run-99"
    assert ingest["azure_worker_vm_size"] == "Standard_E8s_v3"
    assert ingest["max_worker_nodes_provisioned"] == 17
    assert ingest["avg_worker_nodes_consumed"] == 6.0
    assert "avg_worker_vcpus_consumed" in ingest or ingest.get("p95_worker_nodes_consumed") == 6.0
    assert "p99_worker_nodes_consumed" in ingest


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
    # p95 defaults to avg_worker_nodes_consumed=6, 10% buffer -> ceil(6.6)=7
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
    assert out["max_workers"] == 8
    assert "max_workers=8" in out["rationale"]
    assert "auto_termination_minutes=0" in out["rationale"]
