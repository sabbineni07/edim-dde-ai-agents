"""Resolve per-run metrics for recommendations using the same collector as job browse APIs."""

from __future__ import annotations

from typing import Any, Dict, Optional

from DE.src.processors.run_metrics import select_job_run_metrics
from shared.factories.data_collector_context import get_metrics_collector
from shared.factories.data_collector_factory import get_data_collector
from shared.models.job_run_ingest import to_llm_ingest_dict
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _resolve_collector(
    *,
    environment_id: Optional[str],
    user_id: Optional[str],
    connection_id: Optional[str],
    dataset_id: Optional[str] = None,
):
    scoped = get_metrics_collector()
    if scoped is not None:
        return scoped
    if environment_id:
        from DE.src.access.environment_job_metrics_collector import get_collector

        return get_collector(
            environment_id,
            (user_id or "anonymous").strip() or "anonymous",
            connection_id=connection_id,
            dataset_id=dataset_id,
        )
    return get_data_collector()


def fetch_job_run_metrics_for_recommendation(
    *,
    environment_id: Optional[str],
    user_id: Optional[str],
    connection_id: Optional[str],
    dataset_id: Optional[str] = None,
    job_id: str,
    cluster_id: Optional[str] = None,
    job_run_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Load one run's ingest dict; prefers cluster_id, else job_run_id (run-only when dates omitted)."""
    cluster = (cluster_id or "").strip() or None
    workflow = (job_run_id or "").strip() or None
    if not cluster and not workflow:
        return None

    collector = _resolve_collector(
        environment_id=environment_id,
        user_id=user_id,
        connection_id=connection_id,
        dataset_id=dataset_id,
    )
    logger.info(
        "fetch_job_run_metrics_for_recommendation",
        collector=type(collector).__name__,
        environment_id=environment_id,
        dataset_id=dataset_id,
        job_id=job_id,
        cluster_id=cluster,
        job_run_id=workflow if not cluster else None,
        start_date=start_date,
        end_date=end_date,
    )

    rows = collector.collect_job_cluster_metrics(
        start_date=start_date,
        end_date=end_date,
        job_ids=[job_id],
        cluster_id=cluster,
        job_run_id=None if cluster else workflow,
    )
    if not rows:
        return None

    if cluster:
        run_dict = select_job_run_metrics(rows, job_id, cluster)
    else:
        job_id_s = str(job_id)
        workflow_s = str(workflow)
        matches = [
            m for m in rows if str(m.job_id) == job_id_s and str(m.job_run_id or "") == workflow_s
        ]
        if not matches:
            return None
        if len(matches) > 1:
            matches.sort(key=lambda m: m.job_run_duration_seconds, reverse=True)
        from shared.models.job_cluster_metrics import metrics_record_to_dict

        run_dict = metrics_record_to_dict(matches[0])

    if not run_dict:
        return None
    return to_llm_ingest_dict(run_dict)
