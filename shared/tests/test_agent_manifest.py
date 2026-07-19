"""Tests for agent manifest dataset vs connection roles."""

import pytest

from shared.config.agent_manifest import manifest_for_api, role_kind, validate_bindings


def test_manifest_metrics_is_dataset_role():
    manifest = manifest_for_api("dbx_cluster_tuning_agent")
    assert manifest is not None
    metrics = manifest["roles"]["metrics"]
    assert role_kind(metrics) == "dataset"
    assert metrics["schema_profile"] == "job_cluster_metrics"
    assert role_kind(manifest["roles"]["llm"]) == "connection"


def test_spark_rca_manifest_requires_two_datasets():
    manifest = manifest_for_api("spark_job_rca_agent")
    assert manifest is not None
    assert set(manifest["required_roles"]) == {"spark_logs", "spark_metrics", "llm"}
    assert role_kind(manifest["roles"]["spark_logs"]) == "dataset"
    assert manifest["roles"]["spark_logs"]["schema_profile"] == "spark_logs"
    assert manifest["roles"]["spark_metrics"]["schema_profile"] == "spark_metrics"


def test_validate_bindings_accepts_dataset_for_metrics_role():
    ds_id = "11111111-1111-1111-1111-111111111111"
    llm_id = "22222222-2222-2222-2222-222222222222"
    normalized = validate_bindings(
        "dbx_cluster_tuning_agent",
        {"metrics": ds_id, "llm": llm_id},
        connection_types_by_id={llm_id: "ai_foundry"},
        dataset_profiles_by_id={ds_id: "job_cluster_metrics"},
    )
    assert normalized["metrics"] == ds_id
    assert normalized["llm"] == llm_id


def test_validate_bindings_rejects_wrong_dataset_profile():
    ds_id = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValueError, match="schema_profile"):
        validate_bindings(
            "dbx_cluster_tuning_agent",
            {"metrics": ds_id, "llm": "22222222-2222-2222-2222-222222222222"},
            connection_types_by_id={
                "22222222-2222-2222-2222-222222222222": "ai_foundry",
            },
            dataset_profiles_by_id={ds_id: "other_profile"},
        )
