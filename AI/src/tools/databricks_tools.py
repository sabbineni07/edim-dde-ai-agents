"""Databricks data collection tools for LangChain."""

from typing import Any, Dict, Optional

from langchain_core.tools import tool

from DE.src.processors.run_metrics import select_job_run_metrics
from shared.factories.data_collector_factory import get_data_collector
from shared.models.job_run_ingest import to_llm_ingest_dict
from shared.utils.logging import get_logger

logger = get_logger(__name__)


@tool
def get_job_cluster_metrics(
    job_id: str,
    cluster_id: Optional[str] = None,
    job_run_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    """Get job-run ingest metrics for one job run (for sizing recommendations).

    Args:
        job_id: The Databricks job ID
        cluster_id: Cluster/run identifier for this job run
        job_run_id: Deprecated alias for cluster_id
        start_date: Optional YYYY-MM-DD browse window
        end_date: Optional YYYY-MM-DD browse window

    Returns:
        Flat job-run ingest dict for the selected run
    """
    try:
        run_id = (cluster_id or job_run_id or "").strip()
        if not run_id:
            logger.warning("get_job_cluster_metrics_missing_cluster_id", job_id=job_id)
            return {}

        collector = get_data_collector()
        metrics = collector.collect_job_cluster_metrics(
            start_date=start_date,
            end_date=end_date,
            job_ids=[job_id],
            job_run_id=run_id,
        )

        if not metrics:
            logger.warning(
                "get_job_cluster_metrics_empty",
                job_id=job_id,
                cluster_id=run_id,
                start_date=start_date,
                end_date=end_date,
            )
            return {}

        run_dict = select_job_run_metrics(metrics, job_id, run_id)
        if not run_dict:
            return {}

        out = to_llm_ingest_dict(run_dict)
        logger.info(
            "get_job_cluster_metrics_result",
            job_id=job_id,
            cluster_id=run_id,
            avg_worker_nodes_consumed=out.get("avg_worker_nodes_consumed"),
        )
        return out
    except Exception as e:
        logger.error("get_job_cluster_metrics_error", error=str(e))
        return {}


@tool
def get_cost_analysis(
    job_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict:
    """Get cost analysis for a job (observability only; not used for LLM sizing)."""
    try:
        if not start_date or not end_date:
            return {}
        collector = get_data_collector()
        cost_data = collector.collect_cost_data(
            start_date=start_date, end_date=end_date, job_ids=[job_id]
        )
        return cost_data[0] if cost_data else {}
    except Exception as e:
        logger.error("get_cost_analysis_error", error=str(e))
        return {}
