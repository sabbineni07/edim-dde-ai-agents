"""Unit tests for agent content seed and in-memory service."""

import os

os.environ["USE_POSTGRES"] = "false"

from shared.config.agent_content_seed import AGENT_PROMPTS, AGENT_SKILLS
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.services.agent_content_service import (
    get_agent_content,
    list_agent_prompt_versions,
    reset_agent_content_store_for_tests,
    seed_agent_content_if_empty,
    update_agent_prompt,
)


def test_seed_agent_content_in_memory():
    reset_agent_content_store_for_tests()
    count = seed_agent_content_if_empty()
    assert count >= 1
    bundle = get_agent_content(DBX_CLUSTER_TUNING_AGENT_ID)
    assert bundle is not None
    assert bundle.agent_id == DBX_CLUSTER_TUNING_AGENT_ID
    assert len(bundle.prompts) == len(AGENT_PROMPTS)
    assert len(bundle.skills) == len(AGENT_SKILLS)
    assert any(p["chain_name"] == "sizing" and p["role"] == "system" for p in bundle.prompts)
    assert any(s["skill_key"] == "vm_family_rules" for s in bundle.skills)


def test_update_prompt_in_memory():
    reset_agent_content_store_for_tests()
    seed_agent_content_if_empty()
    bundle = get_agent_content(DBX_CLUSTER_TUNING_AGENT_ID)
    assert bundle is not None
    human = next(p for p in bundle.prompts if p["chain_name"] == "sizing" and p["role"] == "human")
    updated = update_agent_prompt(
        DBX_CLUSTER_TUNING_AGENT_ID,
        "sizing",
        "human",
        human["content"],
        updated_by="admin",
    )
    assert updated["version"] == human["version"] + 1
    assert updated["updated_by"] == "admin"
    versions = list_agent_prompt_versions(DBX_CLUSTER_TUNING_AGENT_ID, "sizing", "human")
    assert len(versions) == 2
    assert versions[0]["is_active"] is True
    assert versions[1]["is_active"] is False
