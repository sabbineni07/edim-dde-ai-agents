"""Unit tests for runtime prompt loader."""

import os

os.environ["USE_POSTGRES"] = "false"

from AI.src.core.prompts.loader import (
    build_chain_messages,
    get_guardrail_retry_instruction,
    get_prompt_text,
)
from shared.config.agent_content_seed import AUTO_TERMINATION_PLACEHOLDER
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.config.settings import Settings
from shared.services.agent_content_service import (
    reset_agent_content_store_for_tests,
    seed_agent_content_if_empty,
    update_agent_prompt,
)


def setup_function():
    reset_agent_content_store_for_tests()
    seed_agent_content_if_empty()


def test_build_chain_messages_from_seed():
    settings = Settings(recommendation_auto_termination_minutes=0)
    messages = build_chain_messages(DBX_CLUSTER_TUNING_AGENT_ID, "sizing", settings=settings)
    assert len(messages) == 2
    roles = [m[0] for m in messages]
    assert roles == ["system", "human"]
    system_text = messages[0][1]
    assert AUTO_TERMINATION_PLACEHOLDER not in system_text
    assert "0" in system_text
    human_text = messages[1][1]
    assert "{current_config}" in human_text
    assert "{job_run_ingest}" in human_text


def test_get_prompt_text_uses_updated_store():
    original = get_prompt_text(DBX_CLUSTER_TUNING_AGENT_ID, "guardrail_retry", "system")
    updated = original + " Extra retry guidance."
    update_agent_prompt(
        DBX_CLUSTER_TUNING_AGENT_ID,
        "guardrail_retry",
        "system",
        updated,
        updated_by="admin",
    )
    assert get_prompt_text(DBX_CLUSTER_TUNING_AGENT_ID, "guardrail_retry", "system") == updated
    assert get_guardrail_retry_instruction() == updated


def test_rca_chain_messages_include_skills():
    from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID

    messages = build_chain_messages(SPARK_JOB_RCA_AGENT_ID, "rca")
    assert len(messages) == 2
    system_text = messages[0][1]
    assert "## Domain skills" in system_text
    assert "RCA diagnostic workflow" in system_text
    assert "Reliability & Performance Optimization Specialist" in system_text
    assert "recommendations" in system_text
    assert (
        "RULE: Small file" in system_text
        or "rca_small_files" in system_text
        or "Small file / high metadata" in system_text
    )
    assert "Exit code 137" in system_text or "exit code 137" in system_text
    human_text = messages[1][1]
    assert "{evidence_pack}" in human_text
    assert "{cluster_logs_section}" in human_text
    assert "{spark_metrics_section}" in human_text
    assert "{query_plans_section}" in human_text
    assert "{workspace_id}" in human_text
    assert "one JSON object" in human_text
