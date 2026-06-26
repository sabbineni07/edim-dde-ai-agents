"""Tests for approved RAG document builders."""

from types import SimpleNamespace
from uuid import uuid4


def _sample_rec():
    return SimpleNamespace(
        request_id=uuid4(),
        job_id="job-1",
        job_run_id="run-1",
        workspace_id="ws-1",
        explanation="Use smaller workers for steady CPU.",
        pattern_analysis="CPU under 40% with low memory.",
        reason_codes=["LOW_CPU"],
        comparison={
            "current_configuration": {
                "azure_node_type": "Standard_E8s_v3",
                "autoscale": {"min_workers": 1, "max_workers": 8},
            }
        },
        recommendation={
            "node_type": "Standard_E4s_v3",
            "min_workers": 1,
            "max_workers": 4,
            "rationale": "Right-size cluster for workload",
            "job_run_ingest": {
                "job_type": "ETL",
                "cluster_avg_cpu_utilization_pct_of_ceiling_capacity": 35.2,
                "p95_worker_nodes_consumed": 3,
            },
        },
    )


def test_build_approved_retrieval_text_includes_metrics():
    from shared.rag.approved_document import build_approved_retrieval_text

    text = build_approved_retrieval_text(_sample_rec())
    assert "job_id: job-1" in text
    assert "workload_type: ETL" in text
    assert "cluster_avg_cpu_utilization_pct_of_ceiling_capacity: 35.2" in text
    assert "recommended_node_type: Standard_E4s_v3" in text
    assert "current_node_type: Standard_E8s_v3" in text
    assert "Right-size cluster" in text


def test_build_approved_retrieval_text_includes_lifecycle_notes():
    from shared.rag.approved_document import (
        build_approved_retrieval_text,
        format_lifecycle_adoption_notes,
    )

    events = [
        {
            "to_status": "ACCEPTED",
            "notes": (
                "Databricks cluster sizing adoption — accepted: ETL workload for job job-1, run run-1. "
                "current cluster Standard_E8s_v3, autoscale max 8 workers; "
                "recommended cluster Standard_E4s_v3, autoscale max 4 workers."
            ),
        },
        {
            "to_status": "APPROVED",
            "notes": (
                "Approved Databricks cluster tuning pattern for similar workloads: ETL (job job-1). "
                "Post-deployment monitoring confirmed stable utilization."
            ),
        },
    ]
    formatted = format_lifecycle_adoption_notes(events)
    assert "accepted:" in formatted
    assert "approved:" in formatted

    text = build_approved_retrieval_text(_sample_rec(), lifecycle_events=events)
    assert "adoption_notes:" in text
    assert "Approved Databricks cluster tuning pattern" in text


def test_build_approved_index_payload_stores_ingest():
    from shared.rag.approved_document import build_approved_index_payload

    payload = build_approved_index_payload(_sample_rec())
    assert payload["config_quality"] == "approved"
    assert payload["job_run_ingest"]["job_type"] == "ETL"
    assert "job_run_ingest" not in (payload.get("recommendation") or {})
