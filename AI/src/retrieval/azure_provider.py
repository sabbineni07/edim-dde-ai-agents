"""RAG context using Azure AI Search (existing SearchService API)."""

import json
from typing import TYPE_CHECKING, Any, Dict, List

from AI.src.retrieval.formatting import (
    format_job_pattern_hits_for_cost_chain,
    format_job_patterns_for_pattern_chain,
    format_recommendation_hits_for_cost_chain,
)
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import SearchService

logger = get_logger(__name__)


class AzureSearchRagProvider:
    """Delegates to SearchService.list/search methods; same behavior as pre-refactor chains."""

    def __init__(self, search_service: "SearchService"):
        self._search = search_service

    def cost_chain_historical_context(
        self, pattern_analysis: str, job_cluster_metrics: Dict
    ) -> str:
        query = pattern_analysis if pattern_analysis else str(job_cluster_metrics)
        try:
            similar_recommendations = self._search.search_similar(
                query, top_k=3, filter_quality=True
            )
            recommendations = [
                r
                for r in similar_recommendations
                if r.get("is_recommendation", False) or r.get("document_type") == "recommendation"
            ]
            if recommendations:
                return format_recommendation_hits_for_cost_chain(recommendations)

            similar_jobs = self._search.search_similar_jobs(
                job_cluster_metrics, top_k=3, filter_recommendations=False
            )
            hits = _normalize_job_hits(similar_jobs)
            return format_job_pattern_hits_for_cost_chain(hits)
        except Exception as e:
            logger.warning("azure_rag_cost_context_failed", error=str(e))
            return ""

    def pattern_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        try:
            similar_jobs = self._search.search_similar_jobs(
                job_cluster_metrics, top_k=5, filter_recommendations=False
            )
            hits = _normalize_job_hits(similar_jobs)
            return format_job_patterns_for_pattern_chain(hits)
        except Exception as e:
            logger.warning("azure_rag_pattern_context_failed", error=str(e))
            return ""


def _normalize_job_hits(similar_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ensure each hit has metrics dict and workload_type for formatters."""
    out = []
    for job in similar_jobs:
        if not isinstance(job, dict):
            continue
        metrics = job.get("metrics", {})
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        if not isinstance(metrics, dict):
            metrics = {}
        out.append(
            {
                "metrics": metrics,
                "workload_type": job.get("workload_type", "Unknown"),
                **job,
            }
        )
    return out
