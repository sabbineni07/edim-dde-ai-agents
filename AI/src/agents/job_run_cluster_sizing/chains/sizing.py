"""Cluster sizing chain — pattern analysis + decide in one LLM call (Phase 4.1)."""

import json
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from AI.src.core.retrieval.protocol import RagContextProvider
    from shared.abstractions.protocols import LLMProvider

logger = get_logger(__name__)

PATTERN_ANALYSIS_KEY = "pattern_analysis"

# Required keys for cluster config (guardrails / apply path)
SIZING_RECOMMENDATION_KEYS = (
    "node_family",
    "vcpus",
    "min_workers",
    "max_workers",
    "auto_termination_minutes",
    "rationale",
)

# Full single-call LLM response (pattern + recommendation)
SIZING_LLM_RESPONSE_KEYS = SIZING_RECOMMENDATION_KEYS + (PATTERN_ANALYSIS_KEY,)

# Backward-compatible alias
COST_RECOMMENDATION_KEYS = SIZING_RECOMMENDATION_KEYS


def _extract_json_from_response(text: str) -> Optional[str]:
    """Extract a single JSON object from LLM response (handles markdown code blocks)."""
    if not text or not text.strip():
        return None
    text = text.strip()
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        return code_block.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text


def split_sizing_llm_response(out: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Separate pattern narrative from recommendation fields for guardrails."""
    pattern = str(out.get(PATTERN_ANALYSIS_KEY) or "").strip()
    recommendation = {k: out[k] for k in SIZING_RECOMMENDATION_KEYS if k in out}
    return pattern, recommendation


def _default_pattern_analysis(job_run_ingest: Optional[Dict[str, Any]]) -> str:
    ingest = job_run_ingest or {}
    wt = ingest.get("workload_type", "Unknown")
    cpu = ingest.get("cluster_avg_cpu_utilization_pct_of_ceiling_capacity", "n/a")
    mem = ingest.get("cluster_avg_memory_utilization_pct_of_ceiling_capacity", "n/a")
    p95 = ingest.get("p95_worker_nodes_consumed", "n/a")
    return (
        "### 1. Workload type\n"
        f"- Classified as **{wt}** from ingest.\n\n"
        "### 2. Resource utilization\n"
        f"- Avg CPU % of ceiling: {cpu}; avg memory % of ceiling: {mem}.\n"
        f"- p95 worker nodes consumed: {p95}.\n\n"
        "### 3. Performance characteristics\n"
        "- Fallback summary (LLM parse failed).\n\n"
        "### 4. Optimization opportunities\n"
        "- Re-run recommendation after validating metrics."
    )


class ClusterSizingChain:
    """Single LLM call: workload pattern analysis + cluster sizing JSON (per job run)."""

    def __init__(
        self,
        llm_provider: "LLMProvider",
        rag_provider: Optional["RagContextProvider"] = None,
        use_rag: bool = True,
        settings: Optional[Settings] = None,
    ):
        self.settings: Settings = settings or default_settings  # proxy resolves default agent
        self.llm = llm_provider.get_llm()
        self.rag_provider = rag_provider
        self.use_rag = use_rag and rag_provider is not None
        auto_termination_minutes = int(self.settings.recommendation_auto_termination_minutes or 0)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """## Role
You are a Databricks cluster right-sizing expert. Your output will be parsed as **one JSON object**; no other text is allowed.

## Task
For **one job run**, using job_run_ingest:
1. Analyze workload patterns (CPU, memory, nodes, over/under-provisioned).
2. Recommend optimal cluster configuration (node family, vCPUs, worker range, auto-termination).

Family/SKU fit first, then workers/autoscale. Do not invent metrics.

## Evaluation criteria
- **VM family:** **D** general, **E** memory-heavy, **F** CPU-heavy, **L** storage. Use cluster_avg_*_pct_of_ceiling_capacity, avg_vcpus_utilized_by_workload vs avg_vcpus_allocated_active_cluster, avg_memory_gb_utilized_by_workload vs avg_memory_gb_allocated_active_cluster, peak_*_utilization_pct. Final SKU is validated server-side — output **node_family** and **vcpus** only (no azure_node_type).
- **Workers:** Set max_workers from **p95_worker_nodes_consumed** / **p99_worker_nodes_consumed** plus sizing_policy capacity_buffer_pct. **max_workers** must be **≥ sizing_hints.recommended_max_workers** and **≤ job_run_ingest.max_worker_nodes_cluster_ceiling**. **Do not** set max_workers from workflow_task_count (job-task count, not cluster workers).
- **min_workers** ≤ **max_workers**; **vcpus** in 4–64.
- **Target utilization:** Aim near sizing_policy target_utilization_pct on the limiting resource with buffer — do not under-provision peaks.
- **Auto-termination:** ALWAYS set `auto_termination_minutes` to **"""
                    + str(auto_termination_minutes)
                    + """** — terminate immediately when the job completes.

## Inputs
- **current_config:** azure_worker_vm_size, min_workers, max_workers.
- **job_run_ingest:** Flat JSON (primary source of truth).
- **sizing_hints:** Deterministic pre-check (advisory; ingest wins on conflict).
- **guardrail_feedback:** Retry only — fix listed violations.
- **historical_context:** Optional; secondary only.

## Priorities
- Utilization only (no budget / monthly spend).
- Cite ingest keys in rationale and pattern_analysis.
- Output only valid JSON.

## Output schema (exact keys)
- pattern_analysis: string — markdown with exactly these headings:
  ### 1. Workload type
  ### 2. Resource utilization
  ### 3. Performance characteristics
  ### 4. Optimization opportunities
  (Keep each section short; cite metric numbers.)
- node_family: string, one of "D", "E", "F", "L"
- vcpus: integer (4–64)
- min_workers: integer
- max_workers: integer
- auto_termination_minutes: integer — MUST be """
                    + str(auto_termination_minutes)
                    + """
- rationale: string (2–4 sentences; cite metrics; immediate termination on job completion)""",
                ),
                (
                    "human",
                    """## Input: Current configuration
{current_config}

## Input: Job run ingest (this run only)
{job_run_ingest}

## Input: Sizing hints (pre-check)
{sizing_hints}

## Input: Guardrail feedback (retry only; otherwise None)
{guardrail_feedback}

## Input: Historical context (if any)
{historical_context}

## Instruction
Output one JSON object with keys: pattern_analysis, node_family, vcpus, min_workers, max_workers, auto_termination_minutes, rationale. Set auto_termination_minutes to 0. No markdown outside JSON.""",
                ),
            ]
        )

        self.chain = self.prompt | self.llm | StrOutputParser()

    def _historical_context(self, job_run_ingest: dict) -> str:
        if not self.use_rag or not self.rag_provider:
            return ""
        try:
            if hasattr(self.rag_provider, "sizing_chain_historical_context"):
                return self.rag_provider.sizing_chain_historical_context(job_run_ingest)
            if hasattr(self.rag_provider, "pattern_chain_historical_context"):
                return self.rag_provider.pattern_chain_historical_context(job_run_ingest)
            return self.rag_provider.cost_chain_historical_context("", job_run_ingest)
        except Exception as e:
            logger.warning("rag_search_failed", error=str(e))
            return ""

    def optimize(
        self,
        current_config: dict,
        job_run_ingest: dict,
        sizing_hints: dict,
        pattern_analysis: str = "",  # deprecated: ignored (4.1 merged call)
        guardrail_feedback: Optional[dict] = None,
    ) -> dict:
        """Run merged pattern + sizing LLM; returns full response including pattern_analysis."""
        del pattern_analysis  # unused after 4.1 collapse
        from shared.models.job_run_ingest import format_job_run_ingest_for_llm

        raw = ""
        try:
            historical_context = self._historical_context(job_run_ingest)
            feedback_text = "None"
            if guardrail_feedback:
                feedback_text = format_job_run_ingest_for_llm(guardrail_feedback)

            result = self.chain.invoke(
                {
                    "current_config": format_job_run_ingest_for_llm(current_config),
                    "job_run_ingest": format_job_run_ingest_for_llm(job_run_ingest),
                    "sizing_hints": format_job_run_ingest_for_llm(sizing_hints),
                    "guardrail_feedback": feedback_text,
                    "historical_context": historical_context,
                }
            )
            raw = result if isinstance(result, str) else str(result)
            json_str = _extract_json_from_response(raw)
            if json_str:
                out = json.loads(json_str)
                if isinstance(out, dict) and all(k in out for k in SIZING_LLM_RESPONSE_KEYS):
                    pattern, rec = split_sizing_llm_response(out)
                    if not pattern:
                        pattern = _default_pattern_analysis(job_run_ingest)
                    return {PATTERN_ANALYSIS_KEY: pattern, **rec}
            raise json.JSONDecodeError("Missing or invalid JSON", raw, 0)
        except json.JSONDecodeError:
            try:
                snippet = (raw[:500] + "…") if len(raw) > 500 else raw
            except Exception:
                snippet = ""
            logger.warning("failed_to_parse_json", result=snippet)
            avg_nodes = (job_run_ingest or {}).get("avg_worker_nodes_consumed") or (
                job_run_ingest or {}
            ).get("p95_worker_nodes_consumed")
            max_workers = 8
            if avg_nodes is not None:
                try:
                    max_workers = max(2, min(32, int(float(avg_nodes) + 2)))
                except (TypeError, ValueError):
                    pass
            return {
                PATTERN_ANALYSIS_KEY: _default_pattern_analysis(job_run_ingest),
                "node_family": "E",
                "vcpus": 8,
                "min_workers": 1,
                "max_workers": max_workers,
                "auto_termination_minutes": AUTO_TERMINATION_MINUTES_IMMEDIATE,
                "rationale": "Conservative fallback: parse failed; recommend validating metrics and retrying.",
            }
        except Exception as e:
            logger.error("cluster_sizing_error", error=str(e))
            raise


# Deprecated alias (pre-rename)
CostOptimizationChain = ClusterSizingChain
