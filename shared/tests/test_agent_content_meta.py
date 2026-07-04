"""Tests for agent content usage metadata."""

from shared.config.agent_content_meta import (
    chain_usage,
    enrich_usage_fields,
    prompt_usage,
    skill_usage,
)
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID


def test_prompt_usage_sizing_system():
    meta = prompt_usage(DBX_CLUSTER_TUNING_AGENT_ID, "sizing", "system")
    assert meta is not None
    assert "JSON" in meta["summary"] or "sizing" in meta["summary"].lower()


def test_skill_usage_vm_family():
    meta = skill_usage("vm_family_rules")
    assert meta is not None
    assert "guardrail" in meta["detail"].lower() or "LLM" in meta["detail"]


def test_enrich_usage_fields_adds_keys():
    row = enrich_usage_fields(
        {"chain_name": "sizing", "role": "human", "content": "x"},
        kind="prompt",
        agent_id=DBX_CLUSTER_TUNING_AGENT_ID,
        chain_name="sizing",
        role="human",
    )
    assert row["usage_summary"]
    assert row["usage_detail"]
    assert row["backend_ref"]


def test_chain_usage_sizing():
    meta = chain_usage("sizing")
    assert meta is not None
    assert "ClusterSizingChain" in meta["detail"]
