"""Cluster sizing chain — pattern analysis + decide in one LLM call (Phase 4.1)."""

import json
import re
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from AI.src.core.llm.chat_model_factory import resolve_chain_llm
from AI.src.core.prompts.loader import build_chain_messages
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
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
    metrics = job_run_ingest or {}
    wt = metrics.get("job_type", "Unknown")
    dbr = metrics.get("dbr_version", "n/a")
    drv_cpu = metrics.get("avg_driver_cpu_utilization_pct", "n/a")
    drv_mem = metrics.get("avg_driver_memory_utilization_pct", "n/a")
    cpu = metrics.get("avg_worker_cpu_utilization_pct", "n/a")
    mem = metrics.get("avg_worker_memory_utilization_pct", "n/a")
    p95 = metrics.get("p95_worker_nodes_consumed", "n/a")
    return (
        "### 1. Workload type\n"
        f"- Classified as **{wt}** from ingest.\n"
        f"- Databricks Runtime: **{dbr}**.\n\n"
        "### 2. Resource utilization\n"
        f"- Driver: avg CPU % {drv_cpu}, avg memory % {drv_mem}.\n"
        f"- Workers: avg CPU % {cpu}, avg memory % {mem}; p95 nodes consumed {p95}.\n\n"
        "### 3. Performance characteristics\n"
        "- Fallback summary (LLM parse failed).\n\n"
        "### 4. Optimization opportunities\n"
        "- Re-run recommendation after validating metrics."
    )


class ClusterSizingChain:
    """Single LLM call: workload pattern analysis + cluster sizing JSON (per job run)."""

    def __init__(
        self,
        llm_provider: Optional["LLMProvider"] = None,
        rag_provider: Optional["RagContextProvider"] = None,
        use_rag: bool = True,
        settings: Optional[Settings] = None,
    ):
        self.settings: Settings = settings or default_settings  # proxy resolves default agent
        self.llm = resolve_chain_llm(self.settings, chain="sizing", llm_provider=llm_provider)
        self.rag_provider = rag_provider
        self.use_rag = use_rag and rag_provider is not None

        self.prompt = ChatPromptTemplate.from_messages(
            build_chain_messages(DBX_CLUSTER_TUNING_AGENT_ID, "sizing", settings=self.settings)
        )

        self.chain = self.prompt | self.llm | StrOutputParser()

    def _historical_context(self, job_run_ingest: dict) -> str:
        if not self.use_rag or not self.rag_provider:
            return ""
        try:
            return self.rag_provider.sizing_chain_historical_context(job_run_ingest)
        except Exception as e:
            logger.warning("rag_search_failed", error=str(e))
            return ""

    def optimize(
        self,
        current_config: dict,
        job_run_ingest: dict,
        sizing_hints: dict,
        guardrail_feedback: Optional[dict] = None,
    ) -> dict:
        """Run merged pattern + sizing LLM; returns full response including pattern_analysis."""
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
                "auto_termination_minutes": int(
                    self.settings.recommendation_auto_termination_minutes or 0
                ),
                "rationale": "Conservative fallback: parse failed; recommend validating metrics and retrying.",
            }
        except Exception as e:
            logger.error("cluster_sizing_error", error=str(e))
            raise
