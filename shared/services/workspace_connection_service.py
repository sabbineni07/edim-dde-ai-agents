"""Workspace connection CRUD (non-secret config in JSONB)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.connection_credentials import mask_config_for_response
from shared.config.connection_types import validate_connection_config
from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_CONNECTIONS: Dict[UUID, Dict[str, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    return bool(getattr(settings, "use_postgres", False))


@dataclass(frozen=True)
class WorkspaceConnectionRecord:
    id: UUID
    workspace_id: str
    workspace_name: Optional[str]
    connection_type: str
    name: str
    config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "connection_type": self.connection_type,
            "name": self.name,
            "config": mask_config_for_response(self.config or {}),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class WorkspaceConnectionService:
    def list_connections(
        self, *, workspace_id: str, connection_type: Optional[str] = None
    ) -> List[WorkspaceConnectionRecord]:
        if not _db_enabled():
            rows = [r for r in _MEM_CONNECTIONS.values() if r["workspace_id"] == workspace_id]
            if connection_type:
                rows = [r for r in rows if r["connection_type"] == connection_type]
            return [self._mem_to_record(r) for r in sorted(rows, key=lambda x: x["name"])]

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceConnection

        try:
            session = get_database_session()
            try:
                q = session.query(WorkspaceConnection).filter(
                    WorkspaceConnection.workspace_id == workspace_id
                )
                if connection_type:
                    q = q.filter(WorkspaceConnection.connection_type == connection_type)
                rows = q.order_by(WorkspaceConnection.name.asc()).all()
                return [self._row_to_record(r) for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_connection_list_failed", error=str(e))
            rows = [r for r in _MEM_CONNECTIONS.values() if r["workspace_id"] == workspace_id]
            if connection_type:
                rows = [r for r in rows if r["connection_type"] == connection_type]
            return [self._mem_to_record(r) for r in sorted(rows, key=lambda x: x["name"])]

    def get_connection(self, connection_id: UUID) -> Optional[WorkspaceConnectionRecord]:
        if not _db_enabled():
            row = _MEM_CONNECTIONS.get(connection_id)
            return self._mem_to_record(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceConnection

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceConnection)
                    .filter(WorkspaceConnection.id == connection_id)
                    .first()
                )
                return self._row_to_record(row) if row else None
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_connection_get_failed", error=str(e))
            row = _MEM_CONNECTIONS.get(connection_id)
            return self._mem_to_record(row) if row else None

    def get_connections_by_ids(self, ids: List[UUID]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for cid in ids:
            rec = self.get_connection(cid)
            if rec:
                out.append(
                    {
                        "id": str(rec.id),
                        "connection_type": rec.connection_type,
                        "config": rec.config,
                        "workspace_id": rec.workspace_id,
                    }
                )
        return out

    def create_connection(
        self,
        *,
        workspace_id: str,
        workspace_name: Optional[str],
        connection_type: str,
        name: str,
        config: Dict[str, Any],
    ) -> WorkspaceConnectionRecord:
        clean = validate_connection_config(connection_type, config or {})
        if not _db_enabled():
            now = _utcnow()
            cid = uuid4()
            _MEM_CONNECTIONS[cid] = {
                "id": cid,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "connection_type": connection_type,
                "name": name,
                "config": clean,
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM_CONNECTIONS[cid])

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceConnection

        try:
            session = get_database_session()
            try:
                row = WorkspaceConnection(
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    connection_type=connection_type,
                    name=name,
                    config=clean,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_connection_create_failed", error=str(e))
            now = _utcnow()
            cid = uuid4()
            _MEM_CONNECTIONS[cid] = {
                "id": cid,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "connection_type": connection_type,
                "name": name,
                "config": clean,
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM_CONNECTIONS[cid])

    def update_connection(
        self,
        connection_id: UUID,
        *,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        workspace_name: Optional[str] = None,
    ) -> Optional[WorkspaceConnectionRecord]:
        existing = self.get_connection(connection_id)
        if not existing:
            return None
        clean = None
        if config is not None:
            clean = validate_connection_config(existing.connection_type, config)

        if not _db_enabled():
            row = _MEM_CONNECTIONS.get(connection_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if clean is not None:
                row["config"] = clean
            if workspace_name is not None:
                row["workspace_name"] = workspace_name
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceConnection

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceConnection)
                    .filter(WorkspaceConnection.id == connection_id)
                    .first()
                )
                if not row:
                    return None
                if name is not None:
                    row.name = name
                if clean is not None:
                    row.config = clean
                if workspace_name is not None:
                    row.workspace_name = workspace_name
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_connection_update_failed", error=str(e))
            row = _MEM_CONNECTIONS.get(connection_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if clean is not None:
                row["config"] = clean
            if workspace_name is not None:
                row["workspace_name"] = workspace_name
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

    def delete_connection(self, connection_id: UUID) -> bool:
        if not _db_enabled():
            return _MEM_CONNECTIONS.pop(connection_id, None) is not None

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceConnection

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceConnection)
                    .filter(WorkspaceConnection.id == connection_id)
                    .first()
                )
                if not row:
                    return False
                session.delete(row)
                session.commit()
                return True
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_connection_delete_failed", error=str(e))
            return _MEM_CONNECTIONS.pop(connection_id, None) is not None

    def _row_to_record(self, row) -> WorkspaceConnectionRecord:
        return WorkspaceConnectionRecord(
            id=row.id,
            workspace_id=row.workspace_id,
            workspace_name=row.workspace_name,
            connection_type=row.connection_type,
            name=row.name,
            config=row.config or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _mem_to_record(self, row: Dict[str, Any]) -> WorkspaceConnectionRecord:
        return WorkspaceConnectionRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            workspace_name=row.get("workspace_name"),
            connection_type=row["connection_type"],
            name=row["name"],
            config=row.get("config") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
