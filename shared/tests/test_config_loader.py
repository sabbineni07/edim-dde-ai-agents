"""Tests for YAML-driven platform + agent settings."""

import os
from pathlib import Path

import pytest

from shared.config.loader import (
    get_agent_settings,
    get_platform_settings,
    load_agent_dict,
    load_platform_dict,
    reset_settings_cache,
)
from shared.config.yaml_loader import flatten_agent_yaml, flatten_platform_yaml, resolve_value


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_resolve_env_and_resolver():
    os.environ["TEST_SETTINGS_FOO"] = "bar"
    try:
        assert resolve_value("${env:TEST_SETTINGS_FOO}") == "bar"
        assert resolve_value("${resolve:default_openai_deployment}") is not None
    finally:
        os.environ.pop("TEST_SETTINGS_FOO", None)


def test_platform_yaml_loads():
    flat = load_platform_dict()
    assert flat.get("app_env") == "development"
    assert "vector_retrieval_backend" in flat or flat.get("use_local_data") is True


def test_agent_override_wins_over_platform():
    platform = {"azure_openai_deployment_name": "gpt-4o", "default_confidence_score": 0.5}
    agent = flatten_agent_yaml(
        {
            "llm": {"deployment": "gpt-4o-mini"},
            "sizing": {"default_confidence_score": 0.99},
        }
    )
    merged = {**platform, **agent}
    assert merged["azure_openai_deployment_name"] == "gpt-4o-mini"
    assert merged["default_confidence_score"] == 0.99


def test_agent_settings_merged():
    s = get_agent_settings("job_run_cluster_sizing")
    assert s.recommendation_auto_termination_minutes == 0
    assert s.guardrail_supported_intent == "cluster_recommendation"


def test_platform_settings_cached():
    a = get_platform_settings()
    b = get_platform_settings()
    assert a is b


def test_config_dir_from_env(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    (cfg / "agents").mkdir(parents=True)
    (cfg / "platform.yaml").write_text(
        "platform:\n  app_env: test-env\n",
        encoding="utf-8",
    )
    (cfg / "agents" / "job_run_cluster_sizing.yaml").write_text(
        "sizing:\n  cost_retry_enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_DIR", str(cfg))
    reset_settings_cache()
    plat = get_platform_settings()
    assert plat.app_env == "test-env"
    agent = get_agent_settings("job_run_cluster_sizing")
    assert agent.recommendation_cost_retry_enabled is True
