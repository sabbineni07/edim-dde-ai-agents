"""Persist and look up Spark job RCA analyses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_RCA: Dict[str, Dict[str, Any]] = {}


def reset_rca_store_for_tests() -> None:
    global _MEM_RCA
    _MEM_RCA = {}


def _task_key_norm(task_key: Optional[str]) -> str:
    return (task_key or "").strip()


def _idempotency_key(job_run_id: str, task_key: Optional[str]) -> str:
    return f"{job_run_id}|{_task_key_norm(task_key)}"


def _db_enabled() -> bool:
    return bool(getattr(settings, "use_postgres", True))


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
        }


class RcaAnalysisService:
    def get_by_request_id(self, request_id: UUID) -> Optional[RcaAnalysisRecord]:
        if not _db_enabled():
            for row in _MEM_RCA.values():
                if str(row["request_id"]) == str(request_id):
                    return self._mem_to_record(row)
            return None
        from shared.database.connection import get_database_session
        from shared.database.models import RcaAnalysis

        session = get_database_session()
        try:
            row = session.query(RcaAnalysis).filter(RcaAnalysis.request_id == request_id).first()
            return self._row_to_record(row) if row else None
        finally:
            session.close()

    def get_by_run(
        self, job_run_id: str, task_key: Optional[str] = None
    ) -> Optional[RcaAnalysisRecord]:
        key = _idempotency_key(job_run_id, task_key)
        if not _db_enabled():
            row = _MEM_RCA.get(key)
            return self._mem_to_record(row) if row else None
        from shared.database.connection import get_database_session
        from shared.database.models import RcaAnalysis

        session = get_database_session()
        try:
            row = (
                session.query(RcaAnalysis)
                .filter(
                    RcaAnalysis.job_run_id == job_run_id,
                    RcaAnalysis.task_key_norm == _task_key_norm(task_key),
                )
                .first()
            )
            return self._row_to_record(row) if row else None
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
        from shared.database.models import RcaAnalysis

        session = get_database_session()
        try:
            q = session.query(RcaAnalysis).filter(RcaAnalysis.job_id == job_id)
            if workspace_id:
                q = q.filter(RcaAnalysis.workspace_id == workspace_id)
            rows = q.order_by(RcaAnalysis.created_at.desc()).limit(limit).all()
            return [self._row_to_record(r) for r in rows]
        finally:
            session.close()

    def save(
        self,
        *,
        result: Dict[str, Any],
        trigger_source: Optional[str] = None,
        agent_id: str = "spark_job_rca_agent",
        workspace_agent_id: Optional[str] = None,
        force: bool = False,
    ) -> RcaAnalysisRecord:
        job_run_id = str(result.get("job_run_id") or "").strip()
        if not job_run_id:
            raise ValueError("result.job_run_id is required")
        task_key = result.get("task_key")
        root = result.get("root_cause") or {}
        request_id = UUID(str(result.get("request_id") or uuid4()))
        now = datetime.now(timezone.utc)

        payload = {
            "request_id": request_id,
            "job_id": result.get("job_id"),
            "job_run_id": job_run_id,
            "task_key": task_key,
            "task_key_norm": _task_key_norm(task_key),
            "workspace_id": result.get("workspace_id")
            or (result.get("raw_anchors") or {}).get("workspace_id"),
            "trigger_source": trigger_source,
            "agent_id": agent_id,
            "workspace_agent_id": workspace_agent_id,
            "category": root.get("category"),
            "confidence": root.get("confidence"),
            "summary": root.get("summary"),
            "result": result,
            "created_at": now,
        }

        key = _idempotency_key(job_run_id, task_key)
        if not _db_enabled():
            if not force and key in _MEM_RCA:
                return self._mem_to_record(_MEM_RCA[key])
            _MEM_RCA[key] = payload
            return self._mem_to_record(payload)

        from shared.database.connection import get_database_session
        from shared.database.models import RcaAnalysis

        session = get_database_session()
        try:
            existing = (
                session.query(RcaAnalysis)
                .filter(
                    RcaAnalysis.job_run_id == job_run_id,
                    RcaAnalysis.task_key_norm == _task_key_norm(task_key),
                )
                .first()
            )
            if existing and not force:
                return self._row_to_record(existing)
            if existing and force:
                existing.request_id = request_id
                existing.job_id = payload["job_id"]
                existing.task_key = payload["task_key"]
                existing.workspace_id = payload["workspace_id"]
                existing.trigger_source = payload["trigger_source"]
                existing.agent_id = payload["agent_id"]
                existing.workspace_agent_id = payload["workspace_agent_id"]
                existing.category = payload["category"]
                existing.confidence = payload["confidence"]
                existing.summary = payload["summary"]
                existing.result = payload["result"]
                existing.created_at = now
                session.commit()
                session.refresh(existing)
                return self._row_to_record(existing)

            row = RcaAnalysis(
                request_id=request_id,
                job_id=payload["job_id"],
                job_run_id=job_run_id,
                task_key=payload["task_key"],
                task_key_norm=payload["task_key_norm"],
                workspace_id=payload["workspace_id"],
                trigger_source=payload["trigger_source"],
                agent_id=payload["agent_id"],
                workspace_agent_id=payload["workspace_agent_id"],
                category=payload["category"],
                confidence=payload["confidence"],
                summary=payload["summary"],
                result=payload["result"],
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception as e:
            session.rollback()
            logger.warning("rca_analysis_save_failed", error=str(e))
            # Fall back to memory so pipeline retries still get a response
            _MEM_RCA[key] = payload
            return self._mem_to_record(payload)
        finally:
            session.close()

    def _row_to_record(self, row) -> RcaAnalysisRecord:
        return RcaAnalysisRecord(
            request_id=row.request_id,
            job_id=row.job_id,
            job_run_id=row.job_run_id,
            task_key=row.task_key,
            workspace_id=row.workspace_id,
            trigger_source=row.trigger_source,
            agent_id=row.agent_id,
            workspace_agent_id=row.workspace_agent_id,
            category=row.category,
            confidence=float(row.confidence) if row.confidence is not None else None,
            summary=row.summary,
            result=row.result or {},
            created_at=row.created_at or datetime.now(timezone.utc),
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
            agent_id=row.get("agent_id") or "spark_job_rca_agent",
            workspace_agent_id=row.get("workspace_agent_id"),
            category=row.get("category"),
            confidence=row.get("confidence"),
            summary=row.get("summary"),
            result=row.get("result") or {},
            created_at=row.get("created_at") or datetime.now(timezone.utc),
        )
