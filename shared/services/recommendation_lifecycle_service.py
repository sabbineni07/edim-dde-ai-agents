"""Persist and query recommendation adoption lifecycle transitions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from shared.recommendation_lifecycle import (
    LIFECYCLE_APPROVED,
    LIFECYCLE_RECOMMENDED,
    LIFECYCLE_SUPERSEDED,
    TERMINAL_LIFECYCLE_STATUSES,
    InvalidLifecycleTransitionError,
    allowed_next_statuses,
    normalize_lifecycle_status,
    patch_stored_recommendation_lifecycle,
    utc_now,
    validate_transition,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

try:
    from shared.database.connection import get_database_session
    from shared.database.models import RecommendationHistory, RecommendationLifecycleEvent

    DATABASE_AVAILABLE = True
except Exception as e:
    logger.warning("lifecycle_database_import_failed", error=str(e))
    DATABASE_AVAILABLE = False


class RecommendationLifecycleService:
    """Update adoption lifecycle on recommendation history rows."""

    def get_history(self, request_id: UUID) -> Optional[Any]:
        if not DATABASE_AVAILABLE:
            return None
        session = get_database_session()
        try:
            return (
                session.query(RecommendationHistory)
                .filter(RecommendationHistory.request_id == request_id)
                .first()
            )
        finally:
            session.close()

    def list_events(self, request_id: UUID) -> List[Dict[str, Any]]:
        if not DATABASE_AVAILABLE:
            return []
        session = get_database_session()
        try:
            rows = (
                session.query(RecommendationLifecycleEvent)
                .filter(RecommendationLifecycleEvent.request_id == request_id)
                .order_by(RecommendationLifecycleEvent.changed_at.asc())
                .all()
            )
            return [self._event_to_dict(e) for e in rows]
        finally:
            session.close()

    def list_events_for_requests(self, request_ids: List[UUID]) -> Dict[str, List[Dict[str, Any]]]:
        if not DATABASE_AVAILABLE or not request_ids:
            return {}
        session = get_database_session()
        try:
            rows = (
                session.query(RecommendationLifecycleEvent)
                .filter(RecommendationLifecycleEvent.request_id.in_(request_ids))
                .order_by(RecommendationLifecycleEvent.changed_at.asc())
                .all()
            )
            out: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                key = str(row.request_id)
                out.setdefault(key, []).append(self._event_to_dict(row))
            return out
        finally:
            session.close()

    def transition(
        self,
        request_id: UUID,
        to_status: str,
        changed_by: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not DATABASE_AVAILABLE:
            raise RuntimeError("Database not available for lifecycle updates")

        changed_by = (changed_by or "").strip()
        if not changed_by:
            raise ValueError("changed_by is required")

        session = get_database_session()
        try:
            rec = (
                session.query(RecommendationHistory)
                .filter(RecommendationHistory.request_id == request_id)
                .first()
            )
            if not rec:
                raise LookupError(f"Recommendation not found: {request_id}")

            from_status = normalize_lifecycle_status(rec.lifecycle_status)
            new_status = validate_transition(from_status, to_status)
            now = utc_now()

            event = RecommendationLifecycleEvent(
                request_id=request_id,
                from_status=from_status,
                to_status=new_status,
                changed_by=changed_by,
                changed_at=now,
                notes=(notes or "").strip() or None,
            )
            session.add(event)

            rec.lifecycle_status = new_status
            rec.lifecycle_updated_at = now
            rec.lifecycle_updated_by = changed_by
            rec.recommendation = patch_stored_recommendation_lifecycle(
                rec.recommendation or {},
                status=new_status,
                changed_by=changed_by,
                changed_at=now,
            )

            session.commit()
            logger.info(
                "recommendation_lifecycle_transition",
                request_id=str(request_id),
                from_status=from_status,
                to_status=new_status,
                changed_by=changed_by,
            )
            if new_status == LIFECYCLE_APPROVED:
                try:
                    from shared.rag.approved_indexing import index_approved_recommendation

                    index_approved_recommendation(request_id)
                except Exception as e:
                    logger.warning(
                        "approved_recommendation_indexing_failed",
                        request_id=str(request_id),
                        error=str(e),
                    )
            return {
                "request_id": str(request_id),
                "lifecycle_status": new_status,
                "lifecycle_updated_at": now.isoformat(),
                "lifecycle_updated_by": changed_by,
                "allowed_next_statuses": allowed_next_statuses(new_status),
                "event": self._event_to_dict(event),
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _event_to_dict(event: Any) -> Dict[str, Any]:
        return {
            "id": event.id,
            "request_id": str(event.request_id),
            "from_status": event.from_status,
            "to_status": event.to_status,
            "changed_by": event.changed_by,
            "changed_at": event.changed_at.isoformat() if event.changed_at else None,
            "notes": event.notes,
        }

    @staticmethod
    def record_initial_recommended(
        session: Any,
        request_id: UUID,
        changed_by: str = "system",
    ) -> None:
        """Record RECOMMENDED on insert (same transaction as history row)."""
        now = utc_now()
        event = RecommendationLifecycleEvent(
            request_id=request_id,
            from_status=None,
            to_status=LIFECYCLE_RECOMMENDED,
            changed_by=changed_by,
            changed_at=now,
            notes="Recommendation generated",
        )
        session.add(event)

    def supersede_prior_recommendations(
        self,
        job_id: str,
        job_run_id: str,
        except_request_id: UUID,
    ) -> int:
        """Mark non-terminal prior recommendations for the same run as SUPERSEDED."""
        if not DATABASE_AVAILABLE:
            return 0
        session = get_database_session()
        count = 0
        try:
            rows = (
                session.query(RecommendationHistory)
                .filter(
                    RecommendationHistory.job_id == job_id,
                    RecommendationHistory.job_run_id == job_run_id,
                    RecommendationHistory.request_id != except_request_id,
                )
                .all()
            )
            now = utc_now()
            for rec in rows:
                cur = normalize_lifecycle_status(rec.lifecycle_status)
                if cur in TERMINAL_LIFECYCLE_STATUSES:
                    continue
                try:
                    new_status = validate_transition(cur, LIFECYCLE_SUPERSEDED)
                except InvalidLifecycleTransitionError:
                    continue
                session.add(
                    RecommendationLifecycleEvent(
                        request_id=rec.request_id,
                        from_status=cur,
                        to_status=new_status,
                        changed_by="system",
                        changed_at=now,
                        notes="Superseded by newer recommendation for this run",
                    )
                )
                rec.lifecycle_status = new_status
                rec.lifecycle_updated_at = now
                rec.lifecycle_updated_by = "system"
                rec.recommendation = patch_stored_recommendation_lifecycle(
                    rec.recommendation or {},
                    status=new_status,
                    changed_by="system",
                    changed_at=now,
                )
                count += 1
            if count:
                session.commit()
                logger.info(
                    "superseded_prior_recommendations",
                    job_id=job_id,
                    job_run_id=job_run_id,
                    count=count,
                )
            return count
        except Exception as e:
            session.rollback()
            logger.warning("supersede_prior_recommendations_failed", error=str(e))
            return 0
        finally:
            session.close()
