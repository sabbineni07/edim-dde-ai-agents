"""Workspace agent CRUD and Databricks connection exclusivity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.agent_manifest import get_agent_manifest, validate_bindings
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS
from shared.config.profile_overrides import flatten_overrides, validate_profile_overrides
from shared.config.settings import settings
from shared.services.workspace_connection_service import WorkspaceConnectionService
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_AGENTS: Dict[UUID, Dict[str, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    return bool(getattr(settings, "use_postgres", False))


class DatabricksConnectionInUseError(ValueError):
    """Raised when a Databricks connection is already bound to another workspace agent."""


@dataclass(frozen=True)
class WorkspaceAgentRecord:
    id: UUID
    workspace_id: str
    workspace_name: Optional[str]
    agent_id: str
    name: str
    bindings: Dict[str, Any]
    agent_settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "agent_id": self.agent_id,
            "name": self.name,
            "bindings": self.bindings or {},
            "agent_settings": self.agent_settings or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class WorkspaceAgentService:
    def __init__(self) -> None:
        self._connections = WorkspaceConnectionService()

    def list_agents(
        self, *, workspace_id: str, agent_id: Optional[str] = None
    ) -> List[WorkspaceAgentRecord]:
        if not _db_enabled():
            rows = [r for r in _MEM_AGENTS.values() if r["workspace_id"] == workspace_id]
            if agent_id:
                rows = [r for r in rows if r["agent_id"] == agent_id]
            return [self._mem_to_record(r) for r in sorted(rows, key=lambda x: x["name"])]

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                q = session.query(WorkspaceAgent).filter(
                    WorkspaceAgent.workspace_id == workspace_id
                )
                if agent_id:
                    q = q.filter(WorkspaceAgent.agent_id == agent_id)
                rows = q.order_by(WorkspaceAgent.name.asc()).all()
                return [self._row_to_record(r) for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_agent_list_failed", error=str(e))
            rows = [r for r in _MEM_AGENTS.values() if r["workspace_id"] == workspace_id]
            if agent_id:
                rows = [r for r in rows if r["agent_id"] == agent_id]
            return [self._mem_to_record(r) for r in sorted(rows, key=lambda x: x["name"])]

    def get_agent(self, workspace_agent_id: UUID) -> Optional[WorkspaceAgentRecord]:
        if not _db_enabled():
            row = _MEM_AGENTS.get(workspace_agent_id)
            return self._mem_to_record(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceAgent)
                    .filter(WorkspaceAgent.id == workspace_agent_id)
                    .first()
                )
                return self._row_to_record(row) if row else None
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_agent_get_failed", error=str(e))
            row = _MEM_AGENTS.get(workspace_agent_id)
            return self._mem_to_record(row) if row else None

    def _validate_agent_settings(self, agent_settings: Dict[str, Any]) -> Dict[str, Any]:
        if not agent_settings:
            return {}
        flat = flatten_overrides(agent_settings)
        return validate_profile_overrides(flat, allowed_fields=PROFILE_ALLOWED_FIELDS)

    def _connection_types_for_bindings(
        self, workspace_id: str, bindings: Dict[str, Any]
    ) -> Dict[str, str]:
        types_by_id: Dict[str, str] = {}
        for role, cid in (bindings or {}).items():
            if not cid:
                continue
            rec = self._connections.get_connection(UUID(str(cid)))
            if not rec:
                raise ValueError(f"Connection not found for role {role}: {cid}")
            if rec.workspace_id != workspace_id:
                raise ValueError(f"Connection {cid} does not belong to workspace {workspace_id}")
            types_by_id[str(cid)] = rec.connection_type
        return types_by_id

    def _assert_databricks_exclusivity(
        self,
        bindings: Dict[str, Any],
        types_by_id: Dict[str, str],
        *,
        exclude_workspace_agent_id: Optional[UUID] = None,
    ) -> None:
        metrics_id = bindings.get("metrics")
        if not metrics_id:
            return
        if types_by_id.get(str(metrics_id)) != "databricks":
            return

        all_agents = self._list_all_agents_for_exclusivity_check()
        for wa in all_agents:
            if exclude_workspace_agent_id and wa.id == exclude_workspace_agent_id:
                continue
            other_metrics = (wa.bindings or {}).get("metrics")
            if other_metrics and str(other_metrics) == str(metrics_id):
                raise DatabricksConnectionInUseError(
                    f"Databricks connection {metrics_id} is already bound to workspace agent {wa.id}"
                )

    def _list_all_agents_for_exclusivity_check(self) -> List[WorkspaceAgentRecord]:
        if not _db_enabled():
            return [self._mem_to_record(r) for r in _MEM_AGENTS.values()]

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                rows = session.query(WorkspaceAgent).all()
                return [self._row_to_record(r) for r in rows]
            finally:
                session.close()
        except Exception as e:
            logger.warning("workspace_agent_exclusivity_scan_failed", error=str(e))
            return [self._mem_to_record(r) for r in _MEM_AGENTS.values()]

    def create_agent(
        self,
        *,
        workspace_id: str,
        workspace_name: Optional[str],
        agent_id: str,
        name: str,
        bindings: Dict[str, Any],
        agent_settings: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceAgentRecord:
        if not get_agent_manifest(agent_id):
            raise ValueError(f"Unknown agent_id: {agent_id}")

        types_by_id = self._connection_types_for_bindings(workspace_id, bindings)
        normalized = validate_bindings(agent_id, bindings, types_by_id)
        bindings_out = dict(normalized)
        clean_settings = self._validate_agent_settings(agent_settings or {})
        self._assert_databricks_exclusivity(bindings_out, types_by_id)

        if not _db_enabled():
            now = _utcnow()
            wid = uuid4()
            _MEM_AGENTS[wid] = {
                "id": wid,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "agent_id": agent_id,
                "name": name,
                "bindings": bindings_out,
                "agent_settings": clean_settings,
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM_AGENTS[wid])

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                row = WorkspaceAgent(
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    agent_id=agent_id,
                    name=name,
                    bindings=bindings_out,
                    agent_settings=clean_settings,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except DatabricksConnectionInUseError:
            raise
        except Exception as e:
            logger.warning("workspace_agent_create_failed", error=str(e))
            now = _utcnow()
            wid = uuid4()
            _MEM_AGENTS[wid] = {
                "id": wid,
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "agent_id": agent_id,
                "name": name,
                "bindings": bindings_out,
                "agent_settings": clean_settings,
                "created_at": now,
                "updated_at": now,
            }
            return self._mem_to_record(_MEM_AGENTS[wid])

    def update_agent(
        self,
        workspace_agent_id: UUID,
        *,
        name: Optional[str] = None,
        bindings: Optional[Dict[str, Any]] = None,
        agent_settings: Optional[Dict[str, Any]] = None,
        workspace_name: Optional[str] = None,
    ) -> Optional[WorkspaceAgentRecord]:
        existing = self.get_agent(workspace_agent_id)
        if not existing:
            return None

        bindings_out = existing.bindings
        if bindings is not None:
            types_by_id = self._connection_types_for_bindings(existing.workspace_id, bindings)
            bindings_out = validate_bindings(existing.agent_id, bindings, types_by_id)
            self._assert_databricks_exclusivity(
                bindings_out,
                types_by_id,
                exclude_workspace_agent_id=workspace_agent_id,
            )

        clean_settings = existing.agent_settings
        if agent_settings is not None:
            clean_settings = self._validate_agent_settings(agent_settings)

        if not _db_enabled():
            row = _MEM_AGENTS.get(workspace_agent_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if bindings is not None:
                row["bindings"] = bindings_out
            if agent_settings is not None:
                row["agent_settings"] = clean_settings
            if workspace_name is not None:
                row["workspace_name"] = workspace_name
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceAgent)
                    .filter(WorkspaceAgent.id == workspace_agent_id)
                    .first()
                )
                if not row:
                    return None
                if name is not None:
                    row.name = name
                if bindings is not None:
                    row.bindings = bindings_out
                if agent_settings is not None:
                    row.agent_settings = clean_settings
                if workspace_name is not None:
                    row.workspace_name = workspace_name
                session.commit()
                session.refresh(row)
                return self._row_to_record(row)
            finally:
                session.close()
        except DatabricksConnectionInUseError:
            raise
        except Exception as e:
            logger.warning("workspace_agent_update_failed", error=str(e))
            row = _MEM_AGENTS.get(workspace_agent_id)
            if not row:
                return None
            if name is not None:
                row["name"] = name
            if bindings is not None:
                row["bindings"] = bindings_out
            if agent_settings is not None:
                row["agent_settings"] = clean_settings
            if workspace_name is not None:
                row["workspace_name"] = workspace_name
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

    def delete_agent(self, workspace_agent_id: UUID) -> bool:
        if not _db_enabled():
            return _MEM_AGENTS.pop(workspace_agent_id, None) is not None

        from shared.database.connection import get_database_session
        from shared.database.models import WorkspaceAgent

        try:
            session = get_database_session()
            try:
                row = (
                    session.query(WorkspaceAgent)
                    .filter(WorkspaceAgent.id == workspace_agent_id)
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
            logger.warning("workspace_agent_delete_failed", error=str(e))
            return _MEM_AGENTS.pop(workspace_agent_id, None) is not None

    def resolve_settings_for_agent(self, workspace_agent_id: UUID):
        """Return (agent_id, flat_overrides, secrets) for recommend path."""
        from shared.config.workspace_settings_resolver import resolve_workspace_agent_settings

        rec = self.get_agent(workspace_agent_id)
        if not rec:
            raise LookupError("Workspace agent not found")

        conn_ids = [UUID(v) for v in (rec.bindings or {}).values() if v]
        connections = self._connections.get_connections_by_ids(conn_ids)
        flat, secrets = resolve_workspace_agent_settings(
            agent_id=rec.agent_id,
            bindings=rec.bindings,
            agent_settings=rec.agent_settings,
            connections=connections,
        )
        return rec.agent_id, flat, secrets

    def _row_to_record(self, row) -> WorkspaceAgentRecord:
        return WorkspaceAgentRecord(
            id=row.id,
            workspace_id=row.workspace_id,
            workspace_name=row.workspace_name,
            agent_id=row.agent_id,
            name=row.name,
            bindings=row.bindings or {},
            agent_settings=row.agent_settings or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _mem_to_record(self, row: Dict[str, Any]) -> WorkspaceAgentRecord:
        return WorkspaceAgentRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            workspace_name=row.get("workspace_name"),
            agent_id=row["agent_id"],
            name=row["name"],
            bindings=row.get("bindings") or {},
            agent_settings=row.get("agent_settings") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
