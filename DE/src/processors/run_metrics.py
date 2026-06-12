"""Single job-run metrics selection (no cross-run aggregation for recommendations)."""

from typing import Any, Dict, List, Optional

from shared.models.job_cluster_metrics import JobClusterMetrics, metrics_record_to_dict
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def select_job_run_metrics(
    metrics: List[JobClusterMetrics],
    job_id: str,
    cluster_id: str,
) -> Optional[Dict[str, Any]]:
    """Return one run's metrics dict; match Delta cluster_id for cluster-scoped recommendations."""
    job_id_s = str(job_id)
    cluster_id_s = str(cluster_id)
    matches = [
        m for m in metrics if str(m.job_id) == job_id_s and str(m.cluster_id) == cluster_id_s
    ]
    if not matches:
        logger.warning(
            "job_run_not_found",
            job_id=job_id_s,
            cluster_id=cluster_id_s,
            available_runs=len(metrics),
        )
        return None
    if len(matches) > 1:
        logger.info("multiple_rows_for_job_run", count=len(matches), using="latest_by_duration")
        matches.sort(key=lambda m: m.job_run_duration_seconds, reverse=True)
    return metrics_record_to_dict(matches[0])
