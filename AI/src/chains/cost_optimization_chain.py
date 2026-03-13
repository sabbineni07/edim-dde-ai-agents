"""Cost optimization chain."""

import json
import re
from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import LLMProvider, SearchService

logger = get_logger(__name__)

# Required keys for cost optimization recommendation
COST_RECOMMENDATION_KEYS = (
    "node_family",
    "vcpus",
    "min_workers",
    "max_workers",
    "auto_termination_minutes",
    "rationale",
)


def _extract_json_from_response(text: str) -> Optional[str]:
    """Extract a single JSON object from LLM response (handles markdown code blocks)."""
    if not text or not text.strip():
        return None
    text = text.strip()
    # Remove markdown code block if present
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        return code_block.group(1).strip()
    # Otherwise take first {...} span
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text


class CostOptimizationChain:
    """LangChain for cost optimization recommendations."""

    def __init__(
        self,
        llm_provider: "LLMProvider",
        search_service: Optional["SearchService"] = None,
        use_rag: bool = True,
    ):
        """Initialize cost optimization chain.

        Args:
            llm_provider: LLM provider (e.g. AzureOpenAIService)
            search_service: Optional search service for RAG
            use_rag: If True and search_service provided, use RAG
        """
        self.llm = llm_provider.get_llm()
        self.search_service = search_service
        self.use_rag = use_rag and search_service is not None

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """## Role
You are a cost optimization expert for Databricks clusters. Your output will be parsed as JSON by the application; no other text is allowed.

## Task
Using only the inputs provided below, recommend an optimal cluster configuration (node family, vCPUs, worker range, auto-termination) and output exactly one JSON object with the keys listed under Output schema. Base the recommendation on the job’s actual utilization and the pattern analysis; do not copy historical or similar-job configurations. Apply the evaluation criteria below when choosing node family, vCPUs, and when writing the rationale.

## Evaluation criteria (use these to justify your recommendation)
- **VM family:** Choose one: **D** = General Purpose (balanced CPU/memory, cost-effective); **E** = Memory Optimized (memory-heavy workloads, avoid OOM); **L** = Storage Optimized (high disk throughput); **F** = Compute Optimized (CPU-heavy). Match the family to the workload type and utilization pattern (e.g. high memory utilization -> E; general ETL -> D).
- **CPU and memory:** Specify the vCPU count and consider the CPU:RAM ratio (e.g. 4:1 vs 8:1) to prevent OOM. Use peak_memory_utilization_pct and workload type to decide if memory-optimized (E) or general (D) is appropriate.
- **Databricks disk I/O:** Prefer SKUs that support Premium SSDs (Azure SKUs with **'s'** in the name, e.g. Standard_E4**s**_v3). If the workload benefits from Delta caching or heavy local I/O, note in the rationale whether NVMe local cache is recommended.
- **Version:** Prefer newer generations (v4, v5, v6) over v3 when available for better performance/price; if the current node type is v3, you may recommend staying on v3 or note the benefit of upgrading in the rationale.

## Inputs you will receive
- **Current configuration:** node_type, min_workers, max_workers. This is what the job uses today.
- **Job cluster metrics:** Aggregated metrics (avg_cpu_utilization_pct, peak_cpu_utilization_pct, avg_memory_utilization_pct, peak_memory_utilization_pct, avg_nodes_consumed, p95_nodes_consumed, p99_nodes_consumed, avg_duration_seconds, current_node_type, current_min_workers, current_max_workers, workload_type). Use these as the primary source for right-sizing.
- **Budget constraints:** monthly_budget, current_spend. Consider these as guardrails; do not exceed budget.
- **Pattern analysis:** Text from a previous analysis (workload type, utilization summary, optimization opportunities). Use it to align with workload type and utilization context; do not copy configs from it.
- **Historical context (optional):** Similar jobs or recommendations for context only. Optimize from the current job’s metrics, not from this context.

## Priorities
- Right-size from utilization: low avg/peak CPU and memory -> consider smaller node family or fewer vCPUs; set max_workers near observed usage (e.g. p95_nodes_consumed plus a small buffer), not from historical configs.
- Apply the evaluation criteria above so the rationale addresses VM family choice, CPU/memory (and OOM risk), disk I/O (Premium SSD / NVMe if relevant), and version where applicable.
- Be conservative: avoid under-provisioning; keep a safety margin for peaks.
- Output only valid JSON: no markdown, no code fences, no text before or after the JSON object.

## Output schema (exact keys; values must be valid JSON)
- node_family: string, one of "D", "E", "F", "L"
- vcpus: integer
- min_workers: integer
- max_workers: integer
- auto_termination_minutes: integer or null
- rationale: string (2-4 sentences: cite metrics and briefly address VM family, CPU/memory fit, disk I/O if relevant, and version if relevant)""",
                ),
                (
                    "human",
                    """## Input: Current configuration
{current_config}

## Input: Job cluster metrics
{job_cluster_metrics}

## Input: Budget constraints
{budget_constraints}

## Input: Pattern analysis
{pattern_analysis}

## Input: Historical context (if any)
{historical_context}

## Instruction
Using only the inputs above, output a single JSON object with keys node_family, vcpus, min_workers, max_workers, auto_termination_minutes, rationale. No other text, no markdown.""",
                ),
            ]
        )

        self.chain = self.prompt | self.llm | StrOutputParser()

    def optimize(
        self,
        current_config: dict,
        job_cluster_metrics: dict,
        budget_constraints: dict,
        pattern_analysis: str = "",
    ) -> dict:
        """Generate cost optimization recommendation.

        Args:
            current_config: Current cluster configuration
            job_cluster_metrics: Aggregated job cluster metrics
            budget_constraints: Budget constraints
            pattern_analysis: Pattern analysis from PatternAnalysisChain (optional)
        """
        try:
            historical_context = ""

            # Use RAG to find similar recommendations if enabled
            if self.use_rag and self.search_service:
                try:
                    # First, try to find similar successful recommendations
                    # Only use validated optimal recommendations by default
                    similar_recommendations = self.search_service.search_similar(
                        pattern_analysis if pattern_analysis else str(job_cluster_metrics),
                        top_k=3,
                        filter_quality=True,  # Only use optimal recommendations
                    )

                    # Filter to only recommendations (not raw metrics)
                    recommendations = [
                        r
                        for r in similar_recommendations
                        if r.get("is_recommendation", False)
                        or r.get("document_type") == "recommendation"
                    ]

                    if recommendations:
                        # Build context from successful recommendations
                        rec_contexts = []
                        for rec in recommendations[:3]:  # Top 3
                            rec_data = rec.get("recommendation", {})
                            rec_contexts.append(
                                f"- Recommended: {rec_data.get('node_family', 'N/A')} family, "
                                f"{rec_data.get('vcpus', 'N/A')} vCPUs, "
                                f"{rec_data.get('min_workers', 'N/A')}-{rec_data.get('max_workers', 'N/A')} workers. "
                                f"Rationale: {rec_data.get('rationale', 'N/A')[:100]}"
                            )

                        historical_context = f"""
                        
                        Similar Successful Recommendations Found ({len(recommendations)}):
                        {chr(10).join(rec_contexts)}
                        
                        Use these as guidance, but optimize based on current job's actual needs.
                        """
                    else:
                        # Fallback: find similar job patterns for context
                        similar_jobs = self.search_service.search_similar_jobs(
                            job_cluster_metrics, top_k=3, filter_recommendations=False
                        )

                        if similar_jobs:
                            # Extract patterns only (not configs)
                            patterns = []
                            for job in similar_jobs:
                                metrics = job.get("metrics", {})
                                patterns.append(
                                    {
                                        "cpu": metrics.get("avg_cpu_utilization_pct", 0),
                                        "memory": metrics.get("avg_memory_utilization_pct", 0),
                                        "nodes": metrics.get("avg_nodes_consumed", 0),
                                    }
                                )

                            if patterns:
                                avg_cpu = sum(p["cpu"] for p in patterns) / len(patterns)
                                avg_memory = sum(p["memory"] for p in patterns) / len(patterns)
                                avg_nodes = sum(p["nodes"] for p in patterns) / len(patterns)

                                historical_context = f"""
                                
                                Similar Workload Patterns Found ({len(patterns)} jobs):
                                - Average CPU: {avg_cpu:.1f}%
                                - Average Memory: {avg_memory:.1f}%
                                - Average Nodes: {avg_nodes:.1f}
                                
                                NOTE: These are utilization patterns for context only.
                                Historical configurations may be suboptimal. Optimize based on
                                utilization needs, not by copying historical configs.
                                """
                except Exception as e:
                    logger.warning("rag_search_failed", error=str(e))
                    # Continue without RAG context

            result = self.chain.invoke(
                {
                    "current_config": str(current_config),
                    "job_cluster_metrics": str(job_cluster_metrics),
                    "budget_constraints": str(budget_constraints),
                    "pattern_analysis": (
                        pattern_analysis if pattern_analysis else "No pattern analysis available."
                    ),
                    "historical_context": historical_context,
                }
            )
            raw = result if isinstance(result, str) else str(result)
            json_str = _extract_json_from_response(raw)
            if json_str:
                out = json.loads(json_str)
                if isinstance(out, dict) and all(k in out for k in COST_RECOMMENDATION_KEYS):
                    return out
            raise json.JSONDecodeError("Missing or invalid JSON", raw, 0)
        except json.JSONDecodeError:
            try:
                snippet = (raw[:500] + "…") if len(raw) > 500 else raw
            except Exception:
                snippet = str(result)[:500]
            logger.warning("failed_to_parse_json", result=snippet)
            # Fallback from metrics when possible
            avg_nodes = (job_cluster_metrics or {}).get("avg_nodes_consumed") or (
                job_cluster_metrics or {}
            ).get("p95_nodes_consumed")
            max_workers = 8
            if avg_nodes is not None:
                try:
                    max_workers = max(2, min(32, int(float(avg_nodes) + 2)))
                except (TypeError, ValueError):
                    pass
            return {
                "node_family": "E",
                "vcpus": 8,
                "min_workers": 1,
                "max_workers": max_workers,
                "auto_termination_minutes": None,
                "rationale": "Conservative fallback: parse failed; recommend validating metrics and retrying.",
            }
        except Exception as e:
            logger.error("cost_optimization_error", error=str(e))
            raise
