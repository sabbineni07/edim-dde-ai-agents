"""Workspace agent CRUD; bindings reference environment-scoped connections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.agent_manifest import get_agent_manifest, role_kind, validate_bindings
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS
from shared.config.profile_overrides import flatten_overrides, validate_profile_overrides
from shared.config.settings import settings
from shared.services.environment_connection_service import EnvironmentConnectionService
from shared.services.environment_dataset_service import (
    EnvironmentDatasetService,
    get_environment_dataset,
)
from shared.services.environment_service import resolve_metrics_connection_id
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_AGENTS: Dict[UUID, Dict[str, Any]] = {}


def reset_workspace_agent_store_for_tests() -> None:
    """Clear in-memory workspace agents (unit tests only)."""
    global _MEM_AGENTS
    _MEM_AGENTS = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    import os

    raw = os.environ.get("USE_POSTGRES")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes")
    return bool(getattr(settings, "use_postgres", False))


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
        self._connections = EnvironmentConnectionService()
        self._datasets = EnvironmentDatasetService()

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

    def _binding_metadata_for_validation(
        self, environment_id: str, agent_id: str, bindings: Dict[str, Any]
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        """Return (connection_types_by_id, dataset_profiles_by_id) for validate_bindings."""
        manifest = get_agent_manifest(agent_id)
        if not manifest:
            raise ValueError(f"Unknown agent_id: {agent_id}")

        eid = (environment_id or "").strip()
        if not eid:
            raise ValueError("environment_id is required to validate agent bindings")

        conn_types: Dict[str, str] = {}
        ds_profiles: Dict[str, str] = {}
        roles_spec = manifest.get("roles", {})

        for role, binding_id in (bindings or {}).items():
            if role == "agent_settings" or not binding_id:
                continue
            bid = str(binding_id)
            spec = roles_spec.get(role)

            if role_kind(spec) == "dataset":
                rec = self._datasets.get_dataset(UUID(bid))
                if not rec:
                    raise ValueError(f"Dataset not found for role {role}: {bid}")
                if rec.environment_id != eid:
                    raise ValueError(f"Dataset {bid} does not belong to environment {eid}")
                ds_profiles[bid] = rec.schema_profile
            else:
                rec = self._connections.get_connection(UUID(bid))
                if not rec:
                    raise ValueError(f"Connection not found for role {role}: {bid}")
                if rec.environment_id != eid:
                    raise ValueError(f"Connection {bid} does not belong to environment {eid}")
                conn_types[bid] = rec.connection_type

        return conn_types, ds_profiles

    def _connection_types_for_bindings(
        self, environment_id: str, agent_id: str, bindings: Dict[str, Any]
    ) -> Dict[str, str]:
        conn_types, _ = self._binding_metadata_for_validation(environment_id, agent_id, bindings)
        return conn_types

    def _validate_bindings(
        self, environment_id: str, agent_id: str, bindings: Dict[str, Any]
    ) -> Dict[str, str]:
        conn_types, ds_profiles = self._binding_metadata_for_validation(
            environment_id, agent_id, bindings
        )
        return validate_bindings(agent_id, bindings, conn_types, ds_profiles)

    def get_metrics_dataset_id(self, workspace_agent_id: UUID) -> Optional[str]:
        """Return metrics dataset UUID from agent bindings, if configured."""
        rec = self.get_agent(workspace_agent_id)
        if not rec:
            return None
        manifest = get_agent_manifest(rec.agent_id)
        if not manifest:
            return None
        metrics_spec = manifest.get("roles", {}).get("metrics")
        if role_kind(metrics_spec) != "dataset":
            return None
        metrics_id = (rec.bindings or {}).get("metrics")
        return str(metrics_id).strip() if metrics_id else None

    def create_agent(
        self,
        *,
        environment_id: str,
        workspace_id: str,
        workspace_name: Optional[str],
        agent_id: str,
        name: str,
        bindings: Dict[str, Any],
        agent_settings: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceAgentRecord:
        if not get_agent_manifest(agent_id):
            raise ValueError(f"Unknown agent_id: {agent_id}")

        normalized = self._validate_bindings(environment_id, agent_id, bindings)
        bindings_out = dict(normalized)
        clean_settings = self._validate_agent_settings(agent_settings or {})

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
        environment_id: str,
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
            bindings_out = self._validate_bindings(environment_id, existing.agent_id, bindings)

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

        manifest = get_agent_manifest(rec.agent_id) or {}
        roles_spec = manifest.get("roles", {})
        bindings = rec.bindings or {}

        metrics_dataset: Optional[Dict[str, Any]] = None
        environment_id: Optional[str] = None
        metrics_ds_id = bindings.get("metrics")
        if metrics_ds_id and role_kind(roles_spec.get("metrics")) == "dataset":
            ds_rec = get_environment_dataset(UUID(str(metrics_ds_id)))
            if ds_rec:
                metrics_dataset = ds_rec.to_dict()
                environment_id = ds_rec.environment_id

        conn_ids = [
            UUID(str(v))
            for role, v in bindings.items()
            if v and role_kind(roles_spec.get(role)) == "connection"
        ]
        connections = self._connections.get_connections_by_ids(conn_ids)
        if not environment_id:
            environment_id = next(
                (c.get("environment_id") for c in connections if c.get("environment_id")),
                None,
            )

        metrics_wh_config: Optional[Dict[str, Any]] = None
        if (
            environment_id
            and metrics_dataset
            and metrics_dataset.get("source_type") == "databricks_delta"
        ):
            wh_id = resolve_metrics_connection_id(environment_id, None)
            if wh_id:
                wh = self._connections.get_connection(wh_id)
                metrics_wh_config = dict(wh.config or {}) if wh else None

        flat, secrets = resolve_workspace_agent_settings(
            agent_id=rec.agent_id,
            bindings=bindings,
            agent_settings=rec.agent_settings,
            connections=connections,
            metrics_dataset=metrics_dataset,
            metrics_wh_config=metrics_wh_config,
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
