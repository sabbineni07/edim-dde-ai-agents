"""Jobs and workspaces APIs for the UI."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from DE.src.access.environment_job_metrics_collector import (
    get_collector as get_job_metrics_collector,
)
from shared.database.connection import get_database_session
from shared.database.models import CostUsageLog, RecommendationHistory, RequestLog
from shared.factories.data_collector_factory import get_data_collector
from shared.guardrails.date_range import validate_browse_date_range
from shared.guardrails.exceptions import GuardrailValidationError
from shared.recommendation_lifecycle import (
    allowed_next_statuses,
    lifecycle_display_label,
    normalize_lifecycle_status,
)
from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _resolve_collector(
    environment_id: Optional[str],
    x_user_name: Optional[str],
    x_user_id: Optional[str],
    connection_id: Optional[str] = None,
):
    if environment_id:
        user = (x_user_id or x_user_name or "anonymous").strip() or "anonymous"
        try:
            return get_job_metrics_collector(environment_id, user, connection_id=connection_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    return get_data_collector()


def _default_date_range(start_date: Optional[date], end_date: Optional[date]) -> Dict[str, str]:
    """Normalize and default date range to the last 30 days (inclusive)."""
    today = date.today()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = end_date - timedelta(days=30)
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )
    start_s = start_date.strftime("%Y-%m-%d")
    end_s = end_date.strftime("%Y-%m-%d")
    try:
        validate_browse_date_range(start_s, end_s)
    except GuardrailValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "start_date": start_s,
        "end_date": end_s,
    }


@router.get("/workspaces")
def list_workspaces(
    environment_id: Optional[str] = Query(
        None,
        description="Metrics environment id (dim_dev, local, etc.).",
    ),
    connection_id: Optional[str] = Query(
        None,
        description="Optional metrics connection override (UUID).",
    ),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    """List all distinct workspaces discovered from job metrics.

    Uses the configured data collector (local CSV or Databricks Delta table) to return
    unique workspaces with job counts and overall first/last seen dates (no date filter).
    """
    collector = _resolve_collector(
        environment_id, x_user_name, x_user_id, connection_id=connection_id
    )
    try:
        return collector.list_workspaces()
    except Exception as e:
        logger.error("list_workspaces_error", error=str(e), environment_id=environment_id)
        raise HTTPException(status_code=500, detail="Failed to load workspaces") from e


@router.get("/workspaces/{workspace_id}/jobs")
def list_jobs_for_workspace(
    workspace_id: str,
    start_date: Optional[date] = Query(
        None,
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
    environment_id: Optional[str] = Query(default=None),
    connection_id: Optional[str] = Query(default=None),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    """List jobs for a workspace with aggregated metrics summary."""
    dr = _default_date_range(start_date, end_date)
    collector = _resolve_collector(
        environment_id, x_user_name, x_user_id, connection_id=connection_id
    )
    try:
        return collector.list_jobs_for_workspace(
            workspace_id=workspace_id,
            start_date=dr["start_date"],
            end_date=dr["end_date"],
        )
    except Exception as e:
        logger.error("list_jobs_error", error=str(e), workspace_id=workspace_id)
        raise HTTPException(status_code=500, detail="Failed to load jobs") from e


class JobRunSummary(BaseModel):
    """Per-run metrics summary for the job run picker."""

    cluster_id: str
    job_run_date: Optional[str] = None
    job_run_duration_seconds: Optional[float] = None
    avg_worker_cpu_utilization_pct: Optional[float] = None
    avg_worker_memory_utilization_pct: Optional[float] = None
    avg_worker_nodes_consumed: Optional[float] = None
    total_worker_vcpus_provisioned: Optional[float] = None
    total_worker_memory_gb_provisioned: Optional[float] = None
    peak_worker_cpu_utilization_pct: Optional[float] = None
    peak_worker_memory_utilization_pct: Optional[float] = None
    azure_worker_vm_size: Optional[str] = None
    max_worker_nodes_provisioned: Optional[int] = None
    job_type: Optional[str] = None


@router.get(
    "/workspaces/{workspace_id}/jobs/{job_id}/runs",
    response_model=List[JobRunSummary],
)
def list_job_runs(
    workspace_id: str,
    job_id: str,
    start_date: Optional[date] = Query(
        None,
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
    environment_id: Optional[str] = Query(default=None),
    connection_id: Optional[str] = Query(default=None),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> List[JobRunSummary]:
    """List job runs for a job in a workspace (for run picker in UI)."""
    dr = _default_date_range(start_date, end_date)
    collector = _resolve_collector(
        environment_id, x_user_name, x_user_id, connection_id=connection_id
    )
    if not hasattr(collector, "list_job_runs"):
        raise HTTPException(status_code=501, detail="Job run listing not supported by collector")
    try:
        rows = collector.list_job_runs(
            workspace_id=workspace_id,
            job_id=job_id,
            start_date=dr["start_date"],
            end_date=dr["end_date"],
        )
        return [JobRunSummary(**row) for row in rows]
    except Exception as e:
        logger.error(
            "list_job_runs_error",
            error=str(e),
            workspace_id=workspace_id,
            job_id=job_id,
        )
        raise HTTPException(status_code=500, detail="Failed to load job runs") from e


@router.get("/workspaces/{workspace_id}/jobs/{job_id}/metrics")
def get_job_metrics(
    workspace_id: str,
    job_id: str,
    start_date: Optional[date] = Query(
        None,
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
    environment_id: Optional[str] = Query(default=None),
    connection_id: Optional[str] = Query(default=None),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Get aggregated job cluster metrics for a job in a workspace.

    Returns aggregated job-run metrics for the browse window (utilization,
    nodes consumed, worker VM size, job type, etc.).
    """
    dr = _default_date_range(start_date, end_date)
    collector = _resolve_collector(
        environment_id, x_user_name, x_user_id, connection_id=connection_id
    )
    try:
        agg = collector.get_job_metrics(
            workspace_id=workspace_id,
            job_id=job_id,
            start_date=dr["start_date"],
            end_date=dr["end_date"],
        )
    except Exception as e:
        logger.error(
            "get_job_metrics_error",
            error=str(e),
            workspace_id=workspace_id,
            job_id=job_id,
        )
        raise HTTPException(status_code=500, detail="Failed to load job metrics") from e

    if not agg:
        raise HTTPException(status_code=404, detail="No metrics found for job in date range")

    return {
        "workspace_id": workspace_id,
        "job_id": job_id,
        "start_date": dr["start_date"],
        "end_date": dr["end_date"],
        "metrics": agg,
    }


def _job_run_id_from_history(
    rec: RecommendationHistory,
    req_log: Optional[RequestLog],
) -> Optional[str]:
    """Resolve job_run_id from history row or linked request log (legacy rows)."""
    if rec.job_run_id:
        return str(rec.job_run_id)
    if req_log and req_log.request_params:
        params = req_log.request_params
        if isinstance(params, dict):
            run_id = params.get("job_run_id")
            if run_id is not None and str(run_id).strip():
                return str(run_id).strip()
    return None


class LifecycleEventSummary(BaseModel):
    id: Optional[int] = None
    from_status: Optional[str] = None
    to_status: str
    changed_by: str
    changed_at: Optional[str] = None
    notes: Optional[str] = None


class RecommendationHistoryResponse(BaseModel):
    request_id: str
    job_id: str
    job_run_id: Optional[str] = None
    workspace_id: Optional[str] = None
    timestamp: str
    lifecycle_status: str = "RECOMMENDED"
    lifecycle_status_label: str = "Recommended"
    lifecycle_updated_at: Optional[str] = None
    lifecycle_updated_by: Optional[str] = None
    allowed_next_statuses: List[str] = Field(default_factory=list)
    lifecycle_events: List[LifecycleEventSummary] = Field(default_factory=list)
    api_request_status: Optional[str] = Field(
        default=None,
        description="API call status for POST /recommendations/generate (e.g. success)",
    )
    comparison: Optional[Dict[str, Any]] = None
    reason_codes: List[str] = Field(default_factory=list)
    recommendation: Dict[str, Any]
    explanation: Optional[str] = None
    pattern_analysis: Optional[str] = None
    risk_assessment: Optional[Dict[str, Any]] = None
    token_usage_analysis: Optional[Dict[str, Any]] = None
    request_log: Optional[Dict[str, Any]] = None
    cost_usage_summary: Optional[Dict[str, Any]] = None


@router.get(
    "/workspaces/{workspace_id}/jobs/{job_id}/recommendations",
    response_model=List[RecommendationHistoryResponse],
)
def list_job_recommendations(
    workspace_id: str,
    job_id: str,
    limit: int = Query(
        5,
        ge=1,
        le=50,
        description="Maximum number of recommendation runs to return (most recent first).",
    ),
) -> List[RecommendationHistoryResponse]:
    """Return recent recommendations for a job, joined with request logs and cost usage.

    This powers the UI comparison view: current vs recommended configuration,
    explanation, pattern analysis, and token/cost breakdown.
    """
    try:
        session = get_database_session()
    except Exception as e:
        logger.error("list_job_recommendations_db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Database not available") from e

    try:
        query = (
            session.query(RecommendationHistory, RequestLog)
            .outerjoin(
                RequestLog,
                RecommendationHistory.request_log_request_id == RequestLog.request_id,
            )
            .filter(RecommendationHistory.job_id == job_id)
        )
        if workspace_id:
            query = query.filter(RecommendationHistory.workspace_id == workspace_id)

        rows = query.order_by(RecommendationHistory.timestamp.desc()).limit(limit).all()

        if not rows:
            return []

        lifecycle_svc = RecommendationLifecycleService()
        request_ids: Set[Any] = {rec.request_id for rec, _ in rows}
        events_by_request = lifecycle_svc.list_events_for_requests(list(request_ids))

        # Collect request_ids to fetch cost usage logs
        cost_logs: Dict[Any, List[CostUsageLog]] = {}
        if request_ids:
            logs = (
                session.query(CostUsageLog).filter(CostUsageLog.request_id.in_(request_ids)).all()
            )
            for log in logs:
                cost_logs.setdefault(log.request_id, []).append(log)

        responses: List[RecommendationHistoryResponse] = []
        for rec, req_log in rows:
            req_log_dict: Optional[Dict[str, Any]] = None
            if req_log is not None:
                req_log_dict = {
                    "endpoint": req_log.endpoint,
                    "status": req_log.status,
                    "duration_ms": req_log.duration_ms,
                    "error_code": req_log.error_code,
                    "error_message": req_log.error_message,
                    "timestamp": req_log.timestamp.isoformat() if req_log.timestamp else None,
                }

            # Aggregate cost usage per recommendation request_id
            summary: Optional[Dict[str, Any]] = None
            logs_for_req = cost_logs.get(rec.request_id) or []
            if logs_for_req:
                total_cost = sum(float(l.cost_usd) for l in logs_for_req)
                total_tokens = sum(l.total_tokens for l in logs_for_req)
                by_chain: Dict[str, Dict[str, Any]] = {}
                for l in logs_for_req:
                    chain = l.chain_name
                    entry = by_chain.setdefault(
                        chain,
                        {
                            "model_name": l.model_name,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                            "cost_usd": 0.0,
                        },
                    )
                    entry["input_tokens"] += l.input_tokens
                    entry["output_tokens"] += l.output_tokens
                    entry["total_tokens"] += l.total_tokens
                    entry["cost_usd"] += float(l.cost_usd)

                summary = {
                    "total_cost_usd": total_cost,
                    "total_tokens": total_tokens,
                    "by_chain": by_chain,
                }

            lifecycle_status = normalize_lifecycle_status(rec.lifecycle_status)
            lifecycle_events_raw = events_by_request.get(str(rec.request_id), [])
            lifecycle_events = [
                LifecycleEventSummary(
                    id=e.get("id"),
                    from_status=e.get("from_status"),
                    to_status=e.get("to_status", ""),
                    changed_by=e.get("changed_by", ""),
                    changed_at=e.get("changed_at"),
                    notes=e.get("notes"),
                )
                for e in lifecycle_events_raw
            ]

            responses.append(
                RecommendationHistoryResponse(
                    request_id=str(rec.request_id),
                    job_id=rec.job_id,
                    job_run_id=_job_run_id_from_history(rec, req_log),
                    workspace_id=rec.workspace_id,
                    timestamp=rec.timestamp.isoformat() if rec.timestamp else "",
                    lifecycle_status=lifecycle_status,
                    lifecycle_status_label=lifecycle_display_label(lifecycle_status),
                    lifecycle_updated_at=(
                        rec.lifecycle_updated_at.isoformat() if rec.lifecycle_updated_at else None
                    ),
                    lifecycle_updated_by=rec.lifecycle_updated_by,
                    allowed_next_statuses=allowed_next_statuses(lifecycle_status),
                    lifecycle_events=lifecycle_events,
                    api_request_status=req_log.status if req_log else None,
                    comparison=rec.comparison if isinstance(rec.comparison, dict) else None,
                    reason_codes=list(rec.reason_codes or []),
                    recommendation=rec.recommendation or {},
                    explanation=rec.explanation,
                    pattern_analysis=rec.pattern_analysis,
                    risk_assessment=rec.risk_assessment,
                    token_usage_analysis=rec.token_usage_analysis,
                    request_log=req_log_dict,
                    cost_usage_summary=summary,
                )
            )

        return responses
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "list_job_recommendations_error",
            error=str(e),
            workspace_id=workspace_id,
            job_id=job_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to load recommendation history for job",
        ) from e
    finally:
        try:
            session.close()
        except Exception:
            pass
