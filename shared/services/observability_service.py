"""Observability service: cost/usage logs, request logs, and recommendation history."""

from datetime import date, datetime
from typing import Dict, List, Optional
from uuid import UUID

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

try:
    from shared.database.connection import get_database_session
    from shared.database.models import (
        CostUsageLog,
        DailyCostSummary,
        RecommendationHistory,
        RequestLog,
    )

    DATABASE_AVAILABLE = True
except Exception as e:
    logger.warning("database_import_failed", error=str(e))
    DATABASE_AVAILABLE = False


class ObservabilityService:
    """Logs cost/usage, API requests, and recommendations for observability and analytics."""

    def __init__(self):
        self.enable_app_insights = settings.app_env != "development"

    def log_token_usage(
        self,
        request_id: UUID,
        model_name: str,
        chain_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost_usd: float,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> bool:
        try:
            if self.enable_app_insights:
                self._log_to_app_insights(
                    request_id=request_id,
                    model_name=model_name,
                    chain_name=chain_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                    job_id=job_id,
                )
            if not DATABASE_AVAILABLE:
                return True
            session = get_database_session()
            try:
                cost_log = CostUsageLog(
                    request_id=request_id,
                    job_id=job_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    timestamp=datetime.utcnow(),
                    model_name=model_name,
                    chain_name=chain_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                )
                session.add(cost_log)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("database_logging_error", error=str(e))
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error("cost_logging_error", error=str(e))
            return False

    def log_recommendation(
        self,
        request_id: UUID,
        job_id: str,
        recommendation: Dict,
        explanation: str,
        pattern_analysis: str,
        risk_assessment: Dict,
        token_usage_analysis: Optional[Dict] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        request_log_request_id: Optional[UUID] = None,
    ) -> bool:
        if not DATABASE_AVAILABLE:
            return True
        try:
            session = get_database_session()
            try:
                rec_history = RecommendationHistory(
                    request_id=request_id,
                    job_id=job_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    request_log_request_id=request_log_request_id,
                    timestamp=datetime.utcnow(),
                    recommendation=recommendation,
                    explanation=explanation,
                    pattern_analysis=pattern_analysis,
                    risk_assessment=risk_assessment,
                    token_usage_analysis=token_usage_analysis,
                )
                session.add(rec_history)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("recommendation_logging_error", error=str(e))
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error("recommendation_logging_error", error=str(e))
            return False

    def log_request(
        self,
        request_id: UUID,
        endpoint: str,
        request_params: Dict,
        status: str,
        duration_ms: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> bool:
        """Log an API request (creates a row). Call at request start with status='processing'; use update_request to set final status."""
        if not DATABASE_AVAILABLE:
            return True
        try:
            session = get_database_session()
            try:
                req_log = RequestLog(
                    request_id=request_id,
                    endpoint=endpoint,
                    request_params=request_params or {},
                    status=status,
                    duration_ms=duration_ms,
                    error_code=error_code,
                    error_message=error_message,
                    job_id=job_id,
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
                session.add(req_log)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("request_logging_error", error=str(e))
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error("request_logging_error", error=str(e))
            return False

    def update_request(
        self,
        request_id: UUID,
        status: str,
        duration_ms: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update an existing request_log row (e.g. from 'processing' to 'success' or 'error')."""
        if not DATABASE_AVAILABLE:
            return True
        try:
            from sqlalchemy import update

            session = get_database_session()
            try:
                stmt = (
                    update(RequestLog)
                    .where(RequestLog.request_id == request_id)
                    .values(
                        status=status,
                        duration_ms=duration_ms,
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
                session.execute(stmt)
                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error("request_update_error", error=str(e))
                return False
            finally:
                session.close()
        except Exception as e:
            logger.error("request_update_error", error=str(e))
            return False

    def _log_to_app_insights(
        self,
        request_id,
        model_name,
        chain_name,
        input_tokens,
        output_tokens,
        total_tokens,
        cost_usd,
        job_id=None,
    ):
        logger.info(
            "token_usage",
            request_id=str(request_id),
            model_name=model_name,
            chain_name=chain_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            job_id=job_id,
        )

    def get_daily_summary(self, date: date) -> Optional[Dict]:
        if not DATABASE_AVAILABLE:
            return None
        try:
            session = get_database_session()
            try:
                summary = (
                    session.query(DailyCostSummary).filter(DailyCostSummary.date == date).first()
                )
                if summary:
                    return {
                        "date": summary.date.isoformat(),
                        "total_requests": summary.total_requests,
                        "total_tokens": summary.total_tokens,
                        "total_cost_usd": float(summary.total_cost_usd),
                        "avg_cost_per_request": float(summary.avg_cost_per_request),
                    }
                return None
            finally:
                session.close()
        except Exception as e:
            logger.error("get_daily_summary_error", error=str(e))
            return None

    def get_cost_by_job(self, job_id: str, days: int = 30) -> List[Dict]:
        if not DATABASE_AVAILABLE:
            return []
        try:
            session = get_database_session()
            try:
                from datetime import timedelta

                cutoff_date = datetime.utcnow() - timedelta(days=days)
                logs = (
                    session.query(CostUsageLog)
                    .filter(CostUsageLog.job_id == job_id, CostUsageLog.timestamp >= cutoff_date)
                    .order_by(CostUsageLog.timestamp.desc())
                    .all()
                )
                return [
                    {
                        "timestamp": log.timestamp.isoformat(),
                        "model_name": log.model_name,
                        "chain_name": log.chain_name,
                        "input_tokens": log.input_tokens,
                        "output_tokens": log.output_tokens,
                        "total_tokens": log.total_tokens,
                        "cost_usd": float(log.cost_usd),
                    }
                    for log in logs
                ]
            finally:
                session.close()
        except Exception as e:
            logger.error("get_cost_by_job_error", error=str(e))
            return []
