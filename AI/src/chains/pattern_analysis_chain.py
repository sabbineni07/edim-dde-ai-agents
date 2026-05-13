"""Pattern analysis chain."""

from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from AI.src.retrieval.protocol import RagContextProvider
    from shared.abstractions.protocols import LLMProvider

logger = get_logger(__name__)


class PatternAnalysisChain:
    """LangChain for analyzing workload patterns."""

    def __init__(
        self,
        llm_provider: "LLMProvider",
        rag_provider: Optional["RagContextProvider"] = None,
        use_rag: bool = True,
        use_similar_jobs: bool = False,
    ):
        """Initialize pattern analysis chain.

        Args:
            llm_provider: LLM provider (e.g. AzureOpenAIService)
            rag_provider: Optional retrieval provider for similar-job context
            use_rag: If True and rag_provider provided, RAG can supply historical context
            use_similar_jobs: If True, fetch similar jobs via rag_provider for pattern context.
                Default False: pattern analysis uses only current job metrics (from DataCollector).
                Set True to re-enable similar-jobs context (code path kept for future use).
        """
        self.llm = llm_provider.get_llm()
        self.rag_provider = rag_provider
        self.use_rag = use_rag and rag_provider is not None
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
            if self.use_similar_jobs and self.use_rag and self.rag_provider:
                try:
                    historical_context = self.rag_provider.pattern_chain_historical_context(
                        job_cluster_metrics
                    )
                except Exception as e:
                    logger.warning("rag_search_failed", error=str(e))

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
