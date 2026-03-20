"""Jobs and workspaces APIs for the UI."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from shared.database.connection import get_database_session
from shared.database.models import CostUsageLog, RecommendationHistory, RequestLog
from shared.factories.data_collector_factory import get_data_collector
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


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
    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }


@router.get("/workspaces")
def list_workspaces(
    start_date: Optional[date] = Query(
        None,
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    ),
    end_date: Optional[date] = Query(
        None,
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
) -> List[Dict[str, Any]]:
    """List workspaces discovered from job metrics.

    Uses the configured data collector (local CSV or Databricks Delta table) to scan
    recent job cluster metrics and return unique workspaces with basic summary.
    """
    dr = _default_date_range(start_date, end_date)
    collector = get_data_collector()
    try:
        return collector.list_workspaces(
            start_date=dr["start_date"],
            end_date=dr["end_date"],
        )
    except Exception as e:
        logger.error("list_workspaces_error", error=str(e))
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
) -> List[Dict[str, Any]]:
    """List jobs for a workspace with aggregated metrics summary."""
    dr = _default_date_range(start_date, end_date)
    collector = get_data_collector()
    try:
        return collector.list_jobs_for_workspace(
            workspace_id=workspace_id,
            start_date=dr["start_date"],
            end_date=dr["end_date"],
        )
    except Exception as e:
        logger.error("list_jobs_error", error=str(e), workspace_id=workspace_id)
        raise HTTPException(status_code=500, detail="Failed to load jobs") from e


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
) -> Dict[str, Any]:
    """Get aggregated job cluster metrics for a job in a workspace.

    This returns the same kind of aggregated metrics dict that the recommendation
    agent uses (avg CPU/memory, p95 nodes, workload_type, current_node_type, etc.).
    """
    dr = _default_date_range(start_date, end_date)
    collector = get_data_collector()
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


class RecommendationHistoryResponse(BaseModel):
    request_id: str
    job_id: str
    workspace_id: Optional[str] = None
    timestamp: str
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

        # Collect request_ids to fetch cost usage logs
        request_ids: Set[Any] = {rec.request_id for rec, _ in rows}
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

            responses.append(
                RecommendationHistoryResponse(
                    request_id=str(rec.request_id),
                    job_id=rec.job_id,
                    workspace_id=rec.workspace_id,
                    timestamp=rec.timestamp.isoformat() if rec.timestamp else "",
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
