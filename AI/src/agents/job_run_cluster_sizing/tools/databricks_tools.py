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
    start_date: str,
    end_date: str,
    job_run_id: Optional[str] = None,
) -> Dict:
    """Get job cluster metrics for one job run (not job-wide aggregate).

    Args:
        job_id: The Databricks job ID
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        job_run_id: Required for recommendations — specific run ID

    Returns:
        Dictionary containing metrics for the single run (internal + LLM ingest fields)
    """
    try:
        if not job_run_id or not str(job_run_id).strip():
            logger.warning("get_job_cluster_metrics_missing_job_run_id", job_id=job_id)
            return {}

        collector = get_data_collector()
        metrics = collector.collect_job_cluster_metrics(
            start_date=start_date,
            end_date=end_date,
            job_ids=[job_id],
            job_run_id=str(job_run_id).strip(),
        )

        if not metrics:
            logger.warning(
                "get_job_cluster_metrics_empty",
                job_id=job_id,
                job_run_id=job_run_id,
                start_date=start_date,
                end_date=end_date,
            )
            return {}

        run_dict = select_job_run_metrics(metrics, job_id, str(job_run_id).strip())
        if not run_dict:
            return {}

        ingest = to_llm_ingest_dict(run_dict)
        # Agent uses both internal keys and flat ingest for chains
        out = {**run_dict, **ingest}
        out["job_run_ingest"] = ingest
        logger.info(
            "get_job_cluster_metrics_result",
            job_id=job_id,
            job_run_id=job_run_id,
            workflow_task_count=ingest.get("workflow_task_count"),
        )
        return out
    except Exception as e:
        logger.error("get_job_cluster_metrics_error", error=str(e))
        return {}


@tool
def get_cost_analysis(job_id: str, start_date: str, end_date: str) -> Dict:
    """Get cost analysis for a job (observability only; not used for LLM sizing).

    Args:
        job_id: The Databricks job ID
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dictionary containing cost analysis for the job in the date window
    """
    try:
        collector = get_data_collector()
        cost_data = collector.collect_cost_data(
            start_date=start_date, end_date=end_date, job_ids=[job_id]
        )
        return cost_data[0] if cost_data else {}
    except Exception as e:
        logger.error("get_cost_analysis_error", error=str(e))
        return {}
