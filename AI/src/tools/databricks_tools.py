"""Databricks data collection tools for LangChain."""

from typing import Dict

from langchain_core.tools import tool

from shared.factories.data_collector_factory import get_data_collector
from shared.utils.logging import get_logger

logger = get_logger(__name__)


@tool
def get_job_cluster_metrics(job_id: str, start_date: str, end_date: str) -> Dict:
    """Get job cluster execution metrics for analysis.

    Args:
        job_id: The Databricks job ID
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dictionary containing aggregated job cluster metrics
    """
    try:
        collector = get_data_collector()
        metrics = collector.collect_job_cluster_metrics(
            start_date=start_date, end_date=end_date, job_ids=[job_id]
        )

        if metrics:
            # Aggregate metrics
            from DE.src.processors.metrics_processor import MetricsProcessor

            processor = MetricsProcessor()
            aggregated = processor.aggregate_by_job(metrics)
            out = aggregated.get(job_id, aggregated.get(str(job_id), {}))
            logger.info(
                "get_job_cluster_metrics_result",
                raw_count=len(metrics),
                aggregated_job_ids=list(aggregated.keys()),
                returned_keys=list(out.keys())[:20] if out else [],
            )
            return out
        logger.warning(
            "get_job_cluster_metrics_empty", job_id=job_id, start_date=start_date, end_date=end_date
        )
        return {}
    except Exception as e:
        logger.error("get_job_cluster_metrics_error", error=str(e))
        return {}


@tool
def get_cost_analysis(job_id: str, start_date: str, end_date: str) -> Dict:
    """Get cost analysis for a job.

    Args:
        job_id: The Databricks job ID
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Dictionary containing cost analysis
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
