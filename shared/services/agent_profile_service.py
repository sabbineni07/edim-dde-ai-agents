"""Agent profile persistence and retrieval.

Profiles store *only* JSON overrides (no secrets) that are merged at runtime:
env > profile overrides > agent YAML > platform YAML > defaults.

When Postgres is disabled/unavailable, this service falls back to an in-memory store
so local/CI tests remain green.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    return bool(getattr(settings, "use_postgres", False))


_MEM: Dict[UUID, Dict[str, Any]] = {}


@dataclass(frozen=True)
class AgentProfileRecord:
    id: UUID
    agent_id: str
    name: str
    overrides: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "agent_id": self.agent_id,
            "name": self.name,
            "overrides": self.overrides or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AgentProfileService:
    def list_profiles(self, *, agent_id: Optional[str] = None) -> List[AgentProfileRecord]:
        if not _db_enabled():
            records = list(_MEM.values())
            if agent_id:
                records = [r for r in records if r["agent_id"] == agent_id]
            return [self._mem_to_record(r) for r in sorted(records, key=lambda x: x["name"])]

        from shared.database.connection import get_database_session
        from shared.database.models import AgentProfile

        try:
            session = get_database_session()
            try:
                q = session.query(AgentProfile)
                if agent_id:
                    q = q.filter(AgentProfile.agent_id == agent_id)
                rows = q.order_by(AgentProfile.name.asc()).all()
                return [self._row_to_record(r) for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.warning("agent_profile_db_unavailable_list", error=str(e))
            records = list(_MEM.values())
            if agent_id:
                records = [r for r in records if r["agent_id"] == agent_id]
            return [self._mem_to_record(r) for r in sorted(records, key=lambda x: x["name"])]

    def get_profile(self, profile_id: UUID) -> Optional[AgentProfileRecord]:
        if not _db_enabled():
            row = _MEM.get(profile_id)
            return self._mem_to_record(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import AgentProfile

        try:
            session = get_database_session()
            try:
                row = session.query(AgentProfile).filter(AgentProfile.id == profile_id).first()
                return self._row_to_record(row) if row else None
            finally:
                session.close()
        except Exception as e:
            logger.warning("agent_profile_db_unavailable_get", error=str(e))
            row = _MEM.get(profile_id)
            return self._mem_to_record(row) if row else None

    def create_profile(
        self, *, agent_id: str, name: str, overrides: Dict[str, Any]
    ) -> AgentProfileRecord:
        if not _db_enabled():
            now = _utcnow()
            pid = uuid4()
            _MEM[pid] = {
                "id": pid,
                "agent_id": agent_id,
                "name": name,
                "overrides": overrides or {},
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM[pid])

        from shared.database.connection import get_database_session
        from shared.database.models import AgentProfile

        try:
            session = get_database_session()
            try:
                row = AgentProfile(agent_id=agent_id, name=name, overrides=overrides or {})
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except Exception as e:
            logger.warning("agent_profile_db_unavailable_create", error=str(e))
            now = _utcnow()
            pid = uuid4()
            _MEM[pid] = {
                "id": pid,
                "agent_id": agent_id,
                "name": name,
                "overrides": overrides or {},
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM[pid])

    def update_profile(
        self,
        profile_id: UUID,
        *,
        name: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentProfileRecord]:
        if not _db_enabled():
            row = _MEM.get(profile_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if overrides is not None:
                row["overrides"] = overrides
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import AgentProfile

        try:
            session = get_database_session()
            try:
                row = session.query(AgentProfile).filter(AgentProfile.id == profile_id).first()
                if not row:
                    return None
                if name is not None:
                    row.name = name
                if overrides is not None:
                    row.overrides = overrides
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except Exception as e:
            logger.warning("agent_profile_db_unavailable_update", error=str(e))
            row = _MEM.get(profile_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if overrides is not None:
                row["overrides"] = overrides
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

    def delete_profile(self, profile_id: UUID) -> bool:
        if not _db_enabled():
            return _MEM.pop(profile_id, None) is not None

        from shared.database.connection import get_database_session
        from shared.database.models import AgentProfile

        try:
            session = get_database_session()
            try:
                row = session.query(AgentProfile).filter(AgentProfile.id == profile_id).first()
                if not row:
                    return False
                session.delete(row)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.warning("agent_profile_db_unavailable_delete", error=str(e))
            return _MEM.pop(profile_id, None) is not None

    @staticmethod
    def _row_to_record(row: Any) -> AgentProfileRecord:
        return AgentProfileRecord(
            id=row.id,
            agent_id=row.agent_id,
            name=row.name,
            overrides=row.overrides or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _mem_to_record(row: Dict[str, Any]) -> AgentProfileRecord:
        return AgentProfileRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            name=row["name"],
            overrides=row.get("overrides") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
