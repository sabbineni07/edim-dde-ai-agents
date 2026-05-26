"""RAG context using a local FAISS index (LangChain VectorStore)."""

import json
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.documents import Document

from AI.src.core.retrieval.formatting import (
    format_job_pattern_hits_for_cost_chain,
    format_job_patterns_for_pattern_chain,
    format_recommendation_hits_for_cost_chain,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class FaissRagProvider:
    """Queries FAISS by similarity; expects Documents with metadata aligned to indexed Azure docs."""

    def __init__(self, vectorstore: Any, top_k_recommendations: int = 3, top_k_jobs: int = 5):
        """
        Args:
            vectorstore: langchain_community.vectorstores.FAISS instance
            top_k_recommendations: max recommendation docs to consider
            top_k_jobs: max job_cluster_metrics docs to consider
        """
        self._vs = vectorstore
        self._top_rec = top_k_recommendations
        self._top_jobs = top_k_jobs

    def cost_chain_historical_context(
        self, pattern_analysis: str, job_cluster_metrics: Dict
    ) -> str:
        query = pattern_analysis.strip() if pattern_analysis else str(job_cluster_metrics)
        try:
            docs = self._vs.similarity_search(query, k=max(self._top_rec + self._top_jobs, 6))
            rec_hits = [_doc_to_recommendation_hit(d) for d in docs if _is_rec_doc(d)]
            rec_hits = [h for h in rec_hits if h][: self._top_rec]
            if rec_hits:
                return format_recommendation_hits_for_cost_chain(rec_hits)

            job_hits = [_doc_to_job_hit(d) for d in docs if _is_job_doc(d)]
            job_hits = [h for h in job_hits if h][: self._top_jobs]
            if not job_hits:
                docs_b = self._vs.similarity_search(str(job_cluster_metrics), k=self._top_jobs)
                job_hits = [_doc_to_job_hit(d) for d in docs_b if _is_job_doc(d)]
                job_hits = [h for h in job_hits if h][: self._top_jobs]
            return format_job_pattern_hits_for_cost_chain(job_hits)
        except Exception as e:
            logger.warning("faiss_rag_cost_context_failed", error=str(e))
            return ""

    def pattern_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        return self.sizing_chain_historical_context(job_cluster_metrics)

    def sizing_chain_historical_context(self, job_cluster_metrics: Dict) -> str:
        try:
            docs = self._vs.similarity_search(str(job_cluster_metrics), k=self._top_jobs + 2)
            job_hits = [_doc_to_job_hit(d) for d in docs if _is_job_doc(d)]
            job_hits = [h for h in job_hits if h][: self._top_jobs]
            return format_job_patterns_for_pattern_chain(job_hits)
        except Exception as e:
            logger.warning("faiss_rag_sizing_context_failed", error=str(e))
            return ""


def _is_rec_doc(doc: Document) -> bool:
    md = doc.metadata or {}
    return md.get("document_type") == "recommendation" or md.get("is_recommendation") is True


def _is_job_doc(doc: Document) -> bool:
    md = doc.metadata or {}
    return md.get("document_type") == "job_cluster_metrics"


def _doc_to_recommendation_hit(doc: Document) -> Dict[str, Any]:
    md = doc.metadata or {}
    rec_raw = md.get("recommendation")
    if rec_raw is None and md.get("recommendation_json"):
        rec_raw = md.get("recommendation_json")
    if isinstance(rec_raw, str):
        try:
            rec = json.loads(rec_raw)
        except Exception:
            rec = {}
    elif isinstance(rec_raw, dict):
        rec = rec_raw
    else:
        rec = {}
    return {"document_type": "recommendation", "is_recommendation": True, "recommendation": rec}


def _doc_to_job_hit(doc: Document) -> Dict[str, Any]:
    md = doc.metadata or {}
    metrics_raw = md.get("metrics")
    if isinstance(metrics_raw, str):
        try:
            metrics = json.loads(metrics_raw)
        except Exception:
            metrics = {}
    elif isinstance(metrics_raw, dict):
        metrics = metrics_raw
    else:
        metrics = {}
    return {
        "document_type": "job_cluster_metrics",
        "metrics": metrics,
        "workload_type": md.get("workload_type", "Unknown"),
    }


def load_faiss_vectorstore(index_folder: str, embeddings: Any) -> Any:
    """Load FAISS index from disk (same embeddings model as used at index build time)."""
    from langchain_community.vectorstores import FAISS

    path = Path(index_folder)
    if not path.is_dir():
        raise FileNotFoundError(f"FAISS index folder not found: {path}")
    return FAISS.load_local(
        str(path),
        embeddings,
        allow_dangerous_deserialization=True,
    )
