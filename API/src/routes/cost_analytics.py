"""Cost analytics endpoints."""

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from shared.services.observability_service import ObservabilityService
from shared.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()
observability = ObservabilityService()


@router.get("/daily")
async def get_daily_cost_summary(
    target_date: Optional[date] = Query(
        None, description="Date to get summary for (YYYY-MM-DD). Defaults to today."
    )
):
    """Get daily cost summary.

    Args:
        target_date: Date to get summary for. Defaults to today.

    Returns:
        Daily cost summary
    """
    try:
        if target_date is None:
            target_date = date.today()

        summary = observability.get_daily_summary(target_date)

        if summary is None:
            return {
                "date": target_date.isoformat(),
                "total_requests": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_cost_per_request": 0.0,
            }

        return summary
    except Exception as e:
        logger.error("get_daily_summary_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}")
async def get_job_cost_breakdown(
    job_id: str, days: int = Query(30, ge=1, le=365, description="Number of days to look back")
):
    """Get cost breakdown for a specific job.

    Args:
        job_id: Job ID to query
        days: Number of days to look back (1-365)

    Returns:
        List of cost logs for the job
    """
    try:
        logs = observability.get_cost_by_job(job_id, days)

        # Calculate totals
        total_cost = sum(log["cost_usd"] for log in logs)
        total_tokens = sum(log["total_tokens"] for log in logs)
        total_requests = len(logs)

        return {
            "job_id": job_id,
            "period_days": days,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_cost_per_request": (
                round(total_cost / total_requests, 6) if total_requests > 0 else 0
            ),
            "breakdown": logs,
        }
    except Exception as e:
        logger.error("get_job_cost_breakdown_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_cost_summary(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
):
    """Get cost summary for a date range.

    Args:
        start_date: Start date
        end_date: End date

    Returns:
        Cost summary for the date range
    """
    try:
        from sqlalchemy import func

        from shared.database.connection import get_database_session
        from shared.database.models import CostUsageLog

        session = get_database_session()
        try:
            # Query cost logs in date range
            results = (
                session.query(
                    func.sum(CostUsageLog.total_tokens).label("total_tokens"),
                    func.sum(CostUsageLog.cost_usd).label("total_cost"),
                    func.count(CostUsageLog.id).label("total_requests"),
                )
                .filter(
                    CostUsageLog.timestamp >= datetime.combine(start_date, datetime.min.time()),
                    CostUsageLog.timestamp
                    < datetime.combine(end_date + timedelta(days=1), datetime.min.time()),
                )
                .first()
            )

            total_tokens = results.total_tokens or 0
            total_cost = float(results.total_cost or 0)
            total_requests = results.total_requests or 0

            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_requests": total_requests,
                "total_tokens": total_tokens,
                "total_cost_usd": round(total_cost, 6),
                "avg_cost_per_request": (
                    round(total_cost / total_requests, 6) if total_requests > 0 else 0
                ),
            }
        finally:
            session.close()
    except Exception as e:
        logger.error("get_cost_summary_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
