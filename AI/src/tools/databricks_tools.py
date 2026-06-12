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
    """Get job-run ingest metrics for one cluster execution (for sizing recommendations).

    Args:
        job_id: The Databricks job ID
        cluster_id: Cluster identifier for the job run's attached cluster
        job_run_id: Optional workflow job run ID (used only when cluster_id is omitted)
        start_date: Optional YYYY-MM-DD browse window
        end_date: Optional YYYY-MM-DD browse window

    Returns:
        Flat job-run ingest dict for the selected cluster run
    """
    try:
        cluster = (cluster_id or "").strip()
        workflow_run = (job_run_id or "").strip()
        if not cluster and not workflow_run:
            logger.warning("get_job_cluster_metrics_missing_cluster_id", job_id=job_id)
            return {}

        collector = get_data_collector()
        metrics = collector.collect_job_cluster_metrics(
            start_date=start_date,
            end_date=end_date,
            job_ids=[job_id],
            cluster_id=cluster or None,
            job_run_id=None if cluster else workflow_run or None,
        )

        if not metrics:
            logger.warning(
                "get_job_cluster_metrics_empty",
                job_id=job_id,
                cluster_id=cluster or None,
                job_run_id=workflow_run or None,
                start_date=start_date,
                end_date=end_date,
            )
            return {}

        lookup_cluster = cluster or str(metrics[0].cluster_id)
        run_dict = select_job_run_metrics(metrics, job_id, lookup_cluster)
        if not run_dict:
            return {}

        out = to_llm_ingest_dict(run_dict)
        logger.info(
            "get_job_cluster_metrics_result",
            job_id=job_id,
            cluster_id=lookup_cluster,
            job_run_id=out.get("job_run_id"),
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
