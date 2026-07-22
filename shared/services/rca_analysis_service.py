"""Persist and look up Spark job RCA analyses in recommendations_history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.config.settings import settings
from shared.recommendation_lifecycle import (
    LIFECYCLE_RECOMMENDED,
    LIFECYCLE_SUPERSEDED,
    TERMINAL_LIFECYCLE_STATUSES,
    normalize_lifecycle_status,
    utc_now,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_RCA: Dict[str, Dict[str, Any]] = {}


def reset_rca_store_for_tests() -> None:
    global _MEM_RCA
    _MEM_RCA = {}


def _task_key_norm(task_key: Optional[str]) -> str:
    return (task_key or "").strip()


def _idempotency_key(job_run_id: str, task_key: Optional[str]) -> str:
    return f"{SPARK_JOB_RCA_AGENT_ID}|{job_run_id}|{_task_key_norm(task_key)}"


def _db_enabled() -> bool:
    return bool(getattr(settings, "use_postgres", True))


def _envelope_from_result(
    result: Dict[str, Any],
    *,
    trigger_source: Optional[str],
) -> Dict[str, Any]:
    root = result.get("root_cause") or {}
    return {
        "schema_version": "1.0",
        "kind": "spark_rca",
        "summary": root.get("summary"),
        "category": root.get("category"),
        "confidence": root.get("confidence"),
        "trigger_source": trigger_source,
        "root_cause": root,
        "recommended_actions": result.get("recommended_actions") or [],
        "timeline": result.get("timeline") or [],
        "evidence": result.get("evidence") or [],
        "contributing_factors": result.get("contributing_factors") or [],
        "payload": result,
    }


@dataclass
class RcaAnalysisRecord:
    request_id: UUID
    job_id: Optional[str]
    job_run_id: str
    task_key: Optional[str]
    workspace_id: Optional[str]
    trigger_source: Optional[str]
    agent_id: str
    workspace_agent_id: Optional[str]
    category: Optional[str]
    confidence: Optional[float]
    summary: Optional[str]
    result: Dict[str, Any]
    created_at: datetime
    lifecycle_status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "job_id": self.job_id,
            "job_run_id": self.job_run_id,
            "task_key": self.task_key,
            "workspace_id": self.workspace_id,
            "trigger_source": self.trigger_source,
            "agent_id": self.agent_id,
            "workspace_agent_id": self.workspace_agent_id,
            "category": self.category,
            "confidence": self.confidence,
            "summary": self.summary,
            "result": self.result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "lifecycle_status": self.lifecycle_status,
        }


def _is_open_lifecycle(status: Optional[str]) -> bool:
    try:
        return normalize_lifecycle_status(status) not in TERMINAL_LIFECYCLE_STATUSES
    except ValueError:
        # Unknown/legacy status — treat as open so we do not silently re-run.
        return True


class RcaAnalysisService:
    """RCA persistence backed by recommendations_history (agent_id = spark_job_rca_agent)."""

    def get_by_request_id(self, request_id: UUID) -> Optional[RcaAnalysisRecord]:
        if not _db_enabled():
            for row in _MEM_RCA.values():
                if str(row["request_id"]) == str(request_id):
                    return self._mem_to_record(row)
            return None
        from shared.database.connection import get_database_session
        from shared.database.models import RecommendationHistory

        session = get_database_session()
        try:
            row = (
                session.query(RecommendationHistory)
                .filter(
                    RecommendationHistory.request_id == request_id,
                    RecommendationHistory.agent_id == SPARK_JOB_RCA_AGENT_ID,
                )
                .first()
            )
            return self._row_to_record(row) if row else None
        finally:
            session.close()

    def get_by_run(
        self, job_run_id: str, task_key: Optional[str] = None
    ) -> Optional[RcaAnalysisRecord]:
        key = _idempotency_key(job_run_id, task_key)
        tk = _task_key_norm(task_key)
        if not _db_enabled():
            row = _MEM_RCA.get(key)
            return self._mem_to_record(row) if row else None
        from shared.database.connection import get_database_session
        from shared.database.models import RecommendationHistory

        session = get_database_session()
        try:
            q = session.query(RecommendationHistory).filter(
                RecommendationHistory.agent_id == SPARK_JOB_RCA_AGENT_ID,
                RecommendationHistory.job_run_id == job_run_id,
            )
            if tk:
                q = q.filter(RecommendationHistory.task_key == tk)
            else:
                q = q.filter(
                    (RecommendationHistory.task_key.is_(None))
                    | (RecommendationHistory.task_key == "")
                )
            row = q.order_by(RecommendationHistory.created_at.desc()).first()
            return self._row_to_record(row) if row else None
        finally:
            session.close()

    def get_open_by_run(
        self, job_run_id: str, task_key: Optional[str] = None
    ) -> Optional[RcaAnalysisRecord]:
        """Most recent RCA for this run that is still in a non-terminal lifecycle."""
        key = _idempotency_key(job_run_id, task_key)
        tk = _task_key_norm(task_key)
        if not _db_enabled():
            row = _MEM_RCA.get(key)
            if not row:
                return None
            rec = self._mem_to_record(row)
            return rec if _is_open_lifecycle(rec.lifecycle_status) else None

        from shared.database.connection import get_database_session
        from shared.database.models import RecommendationHistory

        session = get_database_session()
        try:
            q = session.query(RecommendationHistory).filter(
                RecommendationHistory.agent_id == SPARK_JOB_RCA_AGENT_ID,
                RecommendationHistory.job_run_id == job_run_id,
            )
            if tk:
                q = q.filter(RecommendationHistory.task_key == tk)
            else:
                q = q.filter(
                    (RecommendationHistory.task_key.is_(None))
                    | (RecommendationHistory.task_key == "")
                )
            rows = q.order_by(RecommendationHistory.created_at.desc()).limit(20).all()
            for row in rows:
                rec = self._row_to_record(row)
                if _is_open_lifecycle(rec.lifecycle_status):
                    return rec
            return None
        finally:
            session.close()

    def list_for_job(
        self,
        job_id: str,
        *,
        workspace_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[RcaAnalysisRecord]:
        if not _db_enabled():
            rows = [
                self._mem_to_record(r)
                for r in _MEM_RCA.values()
                if str(r.get("job_id") or "") == str(job_id)
                and (not workspace_id or str(r.get("workspace_id") or "") == str(workspace_id))
            ]
            rows.sort(
                key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )
            return rows[:limit]

        from shared.database.connection import get_database_session
        from shared.database.models import RecommendationHistory

        session = get_database_session()
        try:
            q = session.query(RecommendationHistory).filter(
                RecommendationHistory.agent_id == SPARK_JOB_RCA_AGENT_ID,
                RecommendationHistory.job_id == job_id,
            )
            if workspace_id:
                q = q.filter(RecommendationHistory.workspace_id == workspace_id)
            rows = q.order_by(RecommendationHistory.created_at.desc()).limit(limit).all()
            return [self._row_to_record(r) for r in rows]
        finally:
            session.close()

    def save(
        self,
        *,
        result: Dict[str, Any],
        trigger_source: Optional[str] = None,
        agent_id: str = SPARK_JOB_RCA_AGENT_ID,
        workspace_agent_id: Optional[str] = None,
        force: bool = False,
        request_log_request_id: Optional[UUID] = None,
    ) -> RcaAnalysisRecord:
        job_run_id = str(result.get("job_run_id") or "").strip()
        if not job_run_id:
            raise ValueError("result.job_run_id is required")
        task_key = result.get("task_key")
        root = result.get("root_cause") or {}
        request_id = UUID(str(result.get("request_id") or uuid4()))
        now = utc_now()
        envelope = _envelope_from_result(result, trigger_source=trigger_source)

        payload = {
            "request_id": request_id,
            "job_id": result.get("job_id") or "",
            "job_run_id": job_run_id,
            "task_key": task_key,
            "workspace_id": result.get("workspace_id")
            or (result.get("raw_anchors") or {}).get("workspace_id"),
            "trigger_source": trigger_source,
            "agent_id": agent_id or SPARK_JOB_RCA_AGENT_ID,
            "workspace_agent_id": workspace_agent_id,
            "category": root.get("category"),
            "confidence": root.get("confidence"),
            "summary": root.get("summary"),
            "result": result,
            "envelope": envelope,
            "created_at": now,
            "lifecycle_status": LIFECYCLE_RECOMMENDED,
            "request_log_request_id": request_log_request_id,
        }

        key = _idempotency_key(job_run_id, task_key)
        # Only short-circuit on an *open* prior RCA; terminal ones allow a new analysis.
        if not force:
            existing = self.get_open_by_run(job_run_id, task_key)
            if existing:
                return existing

        if not _db_enabled():
            prior = _MEM_RCA.get(key)
            if prior and _is_open_lifecycle(prior.get("lifecycle_status")):
                prior["lifecycle_status"] = LIFECYCLE_SUPERSEDED
            _MEM_RCA[key] = payload
            return self._mem_to_record(payload)

        from shared.database.connection import get_database_session
        from shared.database.models import RecommendationHistory
        from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService

        session = get_database_session()
        try:
            row = RecommendationHistory(
                request_id=request_id,
                request_log_request_id=request_log_request_id,
                job_id=str(payload["job_id"] or job_run_id),
                job_run_id=job_run_id,
                agent_id=payload["agent_id"],
                workspace_agent_id=workspace_agent_id,
                task_key=_task_key_norm(task_key) or None,
                workspace_id=payload["workspace_id"],
                timestamp=now,
                recommendation=envelope,
                explanation=payload["summary"],
                pattern_analysis=None,
                risk_assessment=None,
                token_usage_analysis=result.get("token_usage_analysis"),
                comparison=None,
                reason_codes=None,
                lifecycle_status=LIFECYCLE_RECOMMENDED,
                lifecycle_updated_at=now,
                lifecycle_updated_by="system",
            )
            session.add(row)
            RecommendationLifecycleService.record_initial_recommended(
                session, request_id, changed_by="system"
            )
            session.commit()
            session.refresh(row)
            _MEM_RCA[key] = payload
            record = self._row_to_record(row)
        except Exception as e:
            session.rollback()
            logger.warning("rca_analysis_save_failed", error=str(e))
            _MEM_RCA[key] = payload
            return self._mem_to_record(payload)
        finally:
            session.close()

        try:
            RecommendationLifecycleService().supersede_prior_recommendations(
                job_id=str(payload["job_id"] or job_run_id),
                job_run_id=job_run_id,
                except_request_id=request_id,
                agent_id=payload["agent_id"],
            )
        except Exception as e:
            logger.warning("rca_supersede_prior_failed", error=str(e))
        return record

    def _result_from_recommendation(
        self, recommendation: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not isinstance(recommendation, dict):
            return {}
        payload = recommendation.get("payload")
        if isinstance(payload, dict) and payload.get("job_run_id"):
            return payload
        return recommendation

    def _row_to_record(self, row) -> RcaAnalysisRecord:
        recommendation = row.recommendation if isinstance(row.recommendation, dict) else {}
        result = self._result_from_recommendation(recommendation)
        root = result.get("root_cause") or recommendation.get("root_cause") or {}
        return RcaAnalysisRecord(
            request_id=row.request_id,
            job_id=row.job_id,
            job_run_id=row.job_run_id or "",
            task_key=row.task_key,
            workspace_id=row.workspace_id,
            trigger_source=recommendation.get("trigger_source"),
            agent_id=row.agent_id or SPARK_JOB_RCA_AGENT_ID,
            workspace_agent_id=row.workspace_agent_id,
            category=recommendation.get("category") or root.get("category"),
            confidence=(
                float(recommendation["confidence"])
                if recommendation.get("confidence") is not None
                else (float(root["confidence"]) if root.get("confidence") is not None else None)
            ),
            summary=recommendation.get("summary") or root.get("summary") or row.explanation,
            result=result or recommendation,
            created_at=row.created_at or row.timestamp or datetime.now(timezone.utc),
            lifecycle_status=row.lifecycle_status,
        )

    def _mem_to_record(self, row: Dict[str, Any]) -> RcaAnalysisRecord:
        return RcaAnalysisRecord(
            request_id=(
                row["request_id"]
                if isinstance(row["request_id"], UUID)
                else UUID(str(row["request_id"]))
            ),
            job_id=row.get("job_id"),
            job_run_id=row["job_run_id"],
            task_key=row.get("task_key"),
            workspace_id=row.get("workspace_id"),
            trigger_source=row.get("trigger_source"),
            agent_id=row.get("agent_id") or SPARK_JOB_RCA_AGENT_ID,
            workspace_agent_id=row.get("workspace_agent_id"),
            category=row.get("category"),
            confidence=row.get("confidence"),
            summary=row.get("summary"),
            result=row.get("result") or {},
            created_at=row.get("created_at") or datetime.now(timezone.utc),
            lifecycle_status=row.get("lifecycle_status"),
        )
