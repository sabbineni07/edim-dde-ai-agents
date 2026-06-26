"""Tests for LLM sampling and RAG top-k resolution."""

from types import SimpleNamespace

from shared.config.llm_sampling import resolve_llm_sampling, resolve_rag_top_k


def test_resolve_llm_sampling_global_defaults():
    settings = SimpleNamespace()
    temp, top_p = resolve_llm_sampling(settings, "sizing")
    assert temp == 0.0
    assert top_p == 1.0


def test_resolve_llm_sampling_chain_override():
    settings = SimpleNamespace(
        llm_temperature=0.5,
        llm_top_p=0.9,
        sizing_llm_temperature=0.0,
        explanation_llm_temperature=0.3,
    )
    sizing = resolve_llm_sampling(settings, "sizing")
    explanation = resolve_llm_sampling(settings, "explanation")
    assert sizing == (0.0, 0.9)
    assert explanation == (0.3, 0.9)


def test_resolve_rag_top_k_from_settings():
    settings = SimpleNamespace(rag_top_k_recommendations=5, rag_top_k_jobs=7)
    assert resolve_rag_top_k(settings) == (5, 7)


def test_agent_yaml_flattens_llm_sampling():
    from shared.config.loader import get_agent_settings, reset_settings_cache

    reset_settings_cache()
    settings = get_agent_settings("dbx_cluster_tuning_agent")
    assert settings.llm_temperature == 0
    assert settings.llm_top_p == 1.0
    assert settings.explanation_llm_temperature == 0.2
    assert settings.rag_top_k_recommendations == 3
