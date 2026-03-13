"""Pattern analysis chain."""

from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import LLMProvider, SearchService

logger = get_logger(__name__)


class PatternAnalysisChain:
    """LangChain for analyzing workload patterns."""

    def __init__(
        self,
        llm_provider: "LLMProvider",
        search_service: Optional["SearchService"] = None,
        use_rag: bool = True,
        use_similar_jobs: bool = False,
    ):
        """Initialize pattern analysis chain.

        Args:
            llm_provider: LLM provider (e.g. AzureOpenAIService)
            search_service: Optional search service for RAG
            use_rag: If True and search_service provided, use RAG for historical context
            use_similar_jobs: If True, fetch similar jobs from search for pattern context.
                Default False: pattern analysis uses only current job metrics (from DataCollector).
                Set True to re-enable similar-jobs context (code path kept for future use).
        """
        self.llm = llm_provider.get_llm()
        self.search_service = search_service
        self.use_rag = use_rag and search_service is not None
        self.use_similar_jobs = use_similar_jobs

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """## Role
You are an expert at analyzing Databricks workload patterns. Your analysis will be used by a downstream cost-optimization step to recommend cluster configuration.

## Task
Using only the inputs provided below, produce a structured analysis that:
- Classifies the workload and explains why (citing metrics).
- Summarizes CPU, memory, and node utilization and whether the current configuration is over- or under-provisioned.
- Highlights performance characteristics and optimization opportunities grounded in the numbers.

## Inputs you will receive
- **Job cluster metrics:** A dictionary of aggregated metrics (e.g. avg_cpu_utilization_pct, peak_cpu_utilization_pct, avg_nodes_consumed, p95_nodes_consumed, current_node_type, current_min_workers, current_max_workers, job_duration_seconds, workload_type). Use these as the primary source of truth.
- **Historical context (optional):** If present, similar jobs’ utilization patterns for context only. Do not copy their configurations; base your analysis on the current job’s metrics.

## Priorities
- Be specific: cite numbers from the metrics in every section.
- Prefer the current job’s metrics over historical context when drawing conclusions.
- Keep each section concise; use bullets where appropriate.

## Output structure
Use exactly these markdown headings. Keep each section short.
### 1. Workload type
### 2. Resource utilization
### 3. Performance characteristics
### 4. Optimization opportunities""",
                ),
                (
                    "human",
                    """## Input: Job cluster metrics
{job_cluster_metrics}

## Input: Historical context (if any)
{historical_context}

## Instruction
Using only the job cluster metrics and historical context above, write the structured analysis with the four sections: Workload type, Resource utilization, Performance characteristics, Optimization opportunities. Cite specific numbers from the metrics.""",
                ),
            ]
        )

        self.chain = self.prompt | self.llm | StrOutputParser()

    def analyze(self, job_cluster_metrics: dict) -> str:
        """Analyze job cluster metrics and return pattern analysis.

        Args:
            job_cluster_metrics: Dictionary with job cluster metrics

        Returns:
            Pattern analysis text
        """
        try:
            historical_context = ""

            # Use RAG to find similar jobs if enabled (disabled by default; set use_similar_jobs=True to re-enable)
            if self.use_similar_jobs and self.use_rag and self.search_service:
                try:
                    similar_jobs = self.search_service.search_similar_jobs(
                        job_cluster_metrics, top_k=5, filter_recommendations=False
                    )

                    if similar_jobs:
                        # Extract utilization patterns from similar jobs
                        patterns = []
                        for job in similar_jobs:
                            metrics = job.get("metrics", {})
                            patterns.append(
                                {
                                    "cpu": metrics.get("avg_cpu_utilization_pct", 0),
                                    "memory": metrics.get("avg_memory_utilization_pct", 0),
                                    "nodes": metrics.get("avg_nodes_consumed", 0),
                                    "workload_type": job.get("workload_type", "Unknown"),
                                }
                            )

                        # Build historical context
                        if patterns:
                            avg_cpu = sum(p["cpu"] for p in patterns) / len(patterns)
                            avg_memory = sum(p["memory"] for p in patterns) / len(patterns)
                            avg_nodes = sum(p["nodes"] for p in patterns) / len(patterns)
                            workload_types = [p["workload_type"] for p in patterns]
                            most_common_workload = max(
                                set(workload_types), key=workload_types.count
                            )

                            historical_context = f"""
                            
                            Similar Historical Workload Patterns Found ({len(patterns)} jobs):
                            - Most common workload type: {most_common_workload}
                            - Average CPU utilization: {avg_cpu:.1f}%
                            - Average Memory utilization: {avg_memory:.1f}%
                            - Average nodes consumed: {avg_nodes:.1f}
                            
                            IMPORTANT: These are utilization patterns from similar jobs for context.
                            Historical configurations may be suboptimal. Focus on analyzing the
                            utilization patterns to understand workload needs, not copying historical configs.
                            """
                except Exception as e:
                    logger.warning("rag_search_failed", error=str(e))
                    # Continue without RAG context

            result = self.chain.invoke(
                {
                    "job_cluster_metrics": str(job_cluster_metrics),
                    "historical_context": historical_context,
                }
            )
            logger.info(
                "pattern_analysis_complete",
                used_rag=self.use_rag,
                used_similar_jobs=self.use_similar_jobs,
            )
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error("pattern_analysis_error", error=str(e))
            raise
