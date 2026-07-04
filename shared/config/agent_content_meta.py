"""Usage hints for agent prompts and skills (admin UI + API)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID

UsageMeta = Dict[str, str]

# chain_name -> summary + detail for chain card headers
CHAIN_USAGE: Dict[str, UsageMeta] = {
    "sizing": {
        "summary": "First LLM step: analyze one job run and return sizing JSON.",
        "detail": (
            "Runs inside ClusterSizingChain when you generate a recommendation. "
            "Combines pattern analysis and cluster config in a single LLM call. "
            "Output is parsed as JSON and validated by output guardrails before apply."
        ),
        "backend_ref": "AI/src/agents/dbx_cluster_tuning_agent/chains/sizing.py",
    },
    "explanation": {
        "summary": "Second LLM step: human-readable explanation of the recommendation.",
        "detail": (
            "Runs after sizing and guardrails in RecommendationExplanationChain. "
            "Uses the recommendation, ingest metrics, pattern analysis, and risk assessment "
            "to produce the six-section markdown shown in the UI."
        ),
        "backend_ref": "AI/src/agents/dbx_cluster_tuning_agent/chains/explanation.py",
    },
    "guardrail_retry": {
        "summary": "Retry instruction when sizing output fails guardrail checks.",
        "detail": (
            "Not a full chain. Loaded when should_retry_cost_recommendation is true and "
            "injected into guardrail_feedback.instruction on the sizing human prompt for the retry pass."
        ),
        "backend_ref": "shared/guardrails/retry_policy.py",
    },
}

PROMPT_USAGE: Dict[Tuple[str, str, str], UsageMeta] = {
    (
        DBX_CLUSTER_TUNING_AGENT_ID,
        "sizing",
        "system",
    ): {
        "summary": "System instructions and JSON output contract for sizing.",
        "detail": (
            "Loaded at chain init via build_chain_messages() and sent as the system message. "
            "Defines role, evaluation criteria, and required JSON keys. "
            "{auto_termination_minutes} is replaced from agent settings when the chain is built."
        ),
        "backend_ref": "AI/src/core/prompts/loader.py → ClusterSizingChain",
    },
    (
        DBX_CLUSTER_TUNING_AGENT_ID,
        "sizing",
        "human",
    ): {
        "summary": "Per-run inputs passed into the sizing LLM.",
        "detail": (
            "Template for each recommendation invoke. LangChain fills placeholders from "
            "ClusterSizingChain.optimize(): current_config, job_run_ingest, sizing_hints, "
            "guardrail_feedback (on retry), and historical_context (when RAG is enabled). "
            "All listed placeholders must remain in the template."
        ),
        "backend_ref": "ClusterSizingChain.optimize()",
    },
    (
        DBX_CLUSTER_TUNING_AGENT_ID,
        "explanation",
        "system",
    ): {
        "summary": "Structure and tone for the explanation markdown.",
        "detail": (
            "Loaded at chain init for RecommendationExplanationChain. "
            "Tells the model to use exactly six headings and ground claims in the provided inputs."
        ),
        "backend_ref": "AI/src/core/prompts/loader.py → RecommendationExplanationChain",
    },
    (
        DBX_CLUSTER_TUNING_AGENT_ID,
        "explanation",
        "human",
    ): {
        "summary": "Recommendation context for the explanation LLM.",
        "detail": (
            "Filled per invoke with recommendation JSON, job_run_ingest, pattern_analysis "
            "from sizing, and risk_assessment from guardrails. "
            "Required placeholders must stay in the template."
        ),
        "backend_ref": "RecommendationExplanationChain.explain()",
    },
    (
        DBX_CLUSTER_TUNING_AGENT_ID,
        "guardrail_retry",
        "system",
    ): {
        "summary": "Short retry directive appended to guardrail feedback.",
        "detail": (
            "Loaded by get_guardrail_retry_instruction() and set as instruction inside "
            "guardrail_feedback when the sizing chain retries after fixable guardrail violations."
        ),
        "backend_ref": "shared/guardrails/retry_policy.py → build_guardrail_feedback()",
    },
}

SKILL_USAGE: Dict[str, UsageMeta] = {
    "vm_family_rules": {
        "summary": "Reference: D / E / F / L selection from utilization signals.",
        "detail": (
            "Documented knowledge for admins editing sizing prompts. "
            "Not injected into the LLM automatically today; rules are mirrored in the sizing "
            "system prompt and enforced by server-side guardrails on node_family and vcpus."
        ),
        "backend_ref": "shared/guardrails/output_guardrails.py",
    },
    "sizing_output_schema": {
        "summary": "Reference: required JSON keys from the sizing LLM.",
        "detail": (
            "Documents keys parsed by ClusterSizingChain (SIZING_LLM_RESPONSE_KEYS) and "
            "validated/clamped by output guardrails before the recommendation is stored or applied."
        ),
        "backend_ref": "AI/src/agents/dbx_cluster_tuning_agent/chains/sizing.py",
    },
    "rag_historical_context": {
        "summary": "Reference: how to treat RAG-retrieved examples.",
        "detail": (
            "Guides admins on the {historical_context} placeholder in the sizing human prompt. "
            "At runtime, RAG text is fetched in ClusterSizingChain._historical_context() when "
            "vector retrieval is enabled; job_run_ingest remains the primary source of truth."
        ),
        "backend_ref": "ClusterSizingChain._historical_context()",
    },
    "sku_allowlist": {
        "summary": "Reference: server-side SKU validation and mapping.",
        "detail": (
            "Documents allow-list behavior when the LLM proposes disallowed node types. "
            "Guardrails map to nearest allowed family/vCPU via sku_allowlist — independent of "
            "this stored skill text unless you align prompts with it."
        ),
        "backend_ref": "shared/guardrails/sku_allowlist.py",
    },
}


def chain_usage(chain_name: str) -> Optional[UsageMeta]:
    return CHAIN_USAGE.get(chain_name)


def prompt_usage(agent_id: str, chain_name: str, role: str) -> Optional[UsageMeta]:
    return PROMPT_USAGE.get((agent_id, chain_name, role))


def skill_usage(skill_key: str) -> Optional[UsageMeta]:
    return SKILL_USAGE.get(skill_key)


def enrich_usage_fields(
    row: Dict[str, Any],
    *,
    kind: str,
    agent_id: str,
    chain_name: Optional[str] = None,
    role: Optional[str] = None,
    skill_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach usage_summary, usage_detail, backend_ref when metadata exists."""
    meta: Optional[UsageMeta] = None
    if kind == "prompt" and chain_name and role:
        meta = prompt_usage(agent_id, chain_name, role)
    elif kind == "skill" and skill_key:
        meta = skill_usage(skill_key)

    out = dict(row)
    if meta:
        out["usage_summary"] = meta.get("summary")
        out["usage_detail"] = meta.get("detail")
        out["backend_ref"] = meta.get("backend_ref")
    else:
        out.setdefault("usage_summary", None)
        out.setdefault("usage_detail", None)
        out.setdefault("backend_ref", None)
    return out
