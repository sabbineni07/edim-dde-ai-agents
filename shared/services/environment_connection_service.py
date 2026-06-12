"""Environment-scoped connection CRUD (metrics, llm, rag)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from shared.config.connection_credentials import mask_config_for_response
from shared.config.connection_types import validate_connection_config
from shared.config.loader import get_platform_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

Purpose = Literal["metrics", "llm", "rag"]

PURPOSES = ("metrics", "llm", "rag")

_MEM_CONNECTIONS: Dict[UUID, Dict[str, Any]] = {}
_MEM_ENV_DEFAULTS: Dict[str, Dict[str, UUID]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    raw = os.environ.get("USE_POSTGRES")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes")
    return bool(getattr(get_platform_settings(), "use_postgres", False))


@dataclass(frozen=True)
class EnvironmentConnectionRecord:
    id: UUID
    environment_id: str
    name: str
    connection_type: str
    purpose: str
    config: Dict[str, Any]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        created = self.created_at or _utcnow()
        updated = self.updated_at or created
        return {
            "id": str(self.id),
            "environment_id": self.environment_id,
            "name": self.name,
            "connection_type": self.connection_type,
            "purpose": self.purpose,
            "config": mask_config_for_response(self.config or {}),
            "is_default": self.is_default,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        }


def reset_environment_connection_store_for_tests() -> None:
    """Clear in-memory store (unit tests only)."""
    global _MEM_CONNECTIONS, _MEM_ENV_DEFAULTS
    _MEM_CONNECTIONS = {}
    _MEM_ENV_DEFAULTS = {}


def _databricks_config_from_env_row(item: Dict[str, Any]) -> Dict[str, Any]:
    parts = [
        item.get("catalog_name"),
        item.get("schema_name"),
        item.get("table_name"),
    ]
    table_fqn = ".".join(p for p in parts if p) if all(parts) else ""
    cfg: Dict[str, Any] = {}
    if item.get("databricks_server_hostname"):
        cfg["databricks_server_hostname"] = item["databricks_server_hostname"]
    if item.get("databricks_http_path"):
        cfg["databricks_http_path"] = item["databricks_http_path"]
    if table_fqn:
        cfg["databricks_job_cluster_metrics_table"] = table_fqn
    return cfg


def seed_default_connections_for_environment(
    environment_id: str,
    *,
    display_name: str,
    source_type: str,
    seed_item: Optional[Dict[str, Any]] = None,
) -> Optional[UUID]:
    """Create default metrics connection for databricks_uc envs when missing."""
    if source_type != "databricks_uc":
        return None
    svc = EnvironmentConnectionService()
    existing = svc.list_connections(environment_id=environment_id, purpose="metrics")
    if existing:
        default = next((c for c in existing if c.is_default), existing[0])
        return default.id

    cfg = _databricks_config_from_env_row(seed_item or {})
    rec = svc.create_connection(
        environment_id=environment_id,
        name=display_name,
        connection_type="databricks",
        purpose="metrics",
        config=cfg,
        set_default=True,
        validate=False,
    )
    return rec.id


class EnvironmentConnectionService:
    def list_connections(
        self,
        *,
        environment_id: str,
        purpose: Optional[str] = None,
        connection_type: Optional[str] = None,
    ) -> List[EnvironmentConnectionRecord]:
        eid = (environment_id or "").strip()
        if not eid:
            return []

        if not _db_enabled():
            rows = [r for r in _MEM_CONNECTIONS.values() if r["environment_id"] == eid]
            if purpose:
                rows = [r for r in rows if r["purpose"] == purpose]
            if connection_type:
                rows = [r for r in rows if r["connection_type"] == connection_type]
            return [
                self._mem_to_record(r)
                for r in sorted(rows, key=lambda x: (not x.get("is_default"), x["name"]))
            ]

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow

        session = get_database_session()
        try:
            q = session.query(EnvironmentConnectionRow).filter(
                EnvironmentConnectionRow.environment_id == eid
            )
            if purpose:
                q = q.filter(EnvironmentConnectionRow.purpose == purpose)
            if connection_type:
                q = q.filter(EnvironmentConnectionRow.connection_type == connection_type)
            rows = q.order_by(
                EnvironmentConnectionRow.is_default.desc(),
                EnvironmentConnectionRow.name.asc(),
            ).all()
            return [self._row_to_record(r) for r in rows]
        finally:
            session.close()

    def get_connection(self, connection_id: UUID) -> Optional[EnvironmentConnectionRecord]:
        if not _db_enabled():
            row = _MEM_CONNECTIONS.get(connection_id)
            return self._mem_to_record(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentConnectionRow)
                .filter(EnvironmentConnectionRow.id == connection_id)
                .first()
            )
            return self._row_to_record(row) if row else None
        finally:
            session.close()

    def get_default_connection(
        self, environment_id: str, purpose: Purpose
    ) -> Optional[EnvironmentConnectionRecord]:
        rows = self.list_connections(environment_id=environment_id, purpose=purpose)
        return next((r for r in rows if r.is_default), rows[0] if rows else None)

    def create_connection(
        self,
        *,
        environment_id: str,
        name: str,
        connection_type: str,
        purpose: str,
        config: Dict[str, Any],
        set_default: bool = False,
        validate: bool = True,
    ) -> EnvironmentConnectionRecord:
        if purpose not in PURPOSES:
            raise ValueError(f"Invalid purpose: {purpose}")
        if validate:
            clean = validate_connection_config(connection_type, config or {})
        else:
            clean = dict(config or {})

        if not _db_enabled():
            now = _utcnow()
            cid = uuid4()
            if set_default:
                self._clear_default_mem(environment_id, purpose)
            _MEM_CONNECTIONS[cid] = {
                "id": cid,
                "environment_id": environment_id,
                "name": name,
                "connection_type": connection_type,
                "purpose": purpose,
                "config": clean,
                "is_default": set_default,
                "created_at": now,
                "updated_at": now,
            }
            if set_default:
                _MEM_ENV_DEFAULTS.setdefault(environment_id, {})[purpose] = cid
            return self._mem_to_record(_MEM_CONNECTIONS[cid])

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            if set_default:
                session.query(EnvironmentConnectionRow).filter(
                    EnvironmentConnectionRow.environment_id == environment_id,
                    EnvironmentConnectionRow.purpose == purpose,
                    EnvironmentConnectionRow.is_default.is_(True),
                ).update({"is_default": False})

            row = EnvironmentConnectionRow(
                environment_id=environment_id,
                name=name,
                connection_type=connection_type,
                purpose=purpose,
                config=clean,
                is_default=set_default,
            )
            session.add(row)
            session.flush()

            if set_default:
                env_row = (
                    session.query(PlatformEnvironmentRow)
                    .filter(PlatformEnvironmentRow.id == environment_id)
                    .first()
                )
                if env_row:
                    if purpose == "metrics":
                        env_row.default_metrics_connection_id = row.id
                    elif purpose == "llm":
                        env_row.default_llm_connection_id = row.id

            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_connection(
        self,
        connection_id: UUID,
        *,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Optional[EnvironmentConnectionRecord]:
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
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentConnectionRow)
                .filter(EnvironmentConnectionRow.id == connection_id)
                .first()
            )
            if not row:
                return None
            if name is not None:
                row.name = name
            if clean is not None:
                row.config = clean
            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_connection(self, connection_id: UUID) -> bool:
        existing = self.get_connection(connection_id)
        if not existing:
            return False

        if not _db_enabled():
            row = _MEM_CONNECTIONS.pop(connection_id, None)
            if row and row.get("is_default"):
                defaults = _MEM_ENV_DEFAULTS.get(row["environment_id"], {})
                defaults.pop(row["purpose"], None)
            return row is not None

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentConnectionRow)
                .filter(EnvironmentConnectionRow.id == connection_id)
                .first()
            )
            if not row:
                return False

            env_row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == row.environment_id)
                .first()
            )
            if env_row:
                if env_row.default_metrics_connection_id == row.id:
                    env_row.default_metrics_connection_id = None
                if env_row.default_llm_connection_id == row.id:
                    env_row.default_llm_connection_id = None

            session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_default(self, connection_id: UUID, *, purpose: Purpose) -> EnvironmentConnectionRecord:
        rec = self.get_connection(connection_id)
        if not rec:
            raise ValueError("Connection not found")
        if rec.purpose != purpose:
            raise ValueError(f"Connection purpose is '{rec.purpose}', not '{purpose}'")

        if not _db_enabled():
            self._clear_default_mem(rec.environment_id, purpose)
            row = _MEM_CONNECTIONS[connection_id]
            row["is_default"] = True
            row["updated_at"] = _utcnow()
            _MEM_ENV_DEFAULTS.setdefault(rec.environment_id, {})[purpose] = connection_id
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentConnectionRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            session.query(EnvironmentConnectionRow).filter(
                EnvironmentConnectionRow.environment_id == rec.environment_id,
                EnvironmentConnectionRow.purpose == purpose,
                EnvironmentConnectionRow.is_default.is_(True),
            ).update({"is_default": False})

            row = (
                session.query(EnvironmentConnectionRow)
                .filter(EnvironmentConnectionRow.id == connection_id)
                .first()
            )
            if not row:
                raise ValueError("Connection not found")
            row.is_default = True

            env_row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == rec.environment_id)
                .first()
            )
            if env_row:
                if purpose == "metrics":
                    env_row.default_metrics_connection_id = row.id
                elif purpose == "llm":
                    env_row.default_llm_connection_id = row.id

            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _clear_default_mem(self, environment_id: str, purpose: str) -> None:
        for row in _MEM_CONNECTIONS.values():
            if row["environment_id"] == environment_id and row["purpose"] == purpose:
                row["is_default"] = False

    def _row_to_record(self, row) -> EnvironmentConnectionRecord:
        now = _utcnow()
        return EnvironmentConnectionRecord(
            id=row.id,
            environment_id=row.environment_id,
            name=row.name,
            connection_type=row.connection_type,
            purpose=row.purpose,
            config=row.config or {},
            is_default=bool(row.is_default),
            created_at=row.created_at or now,
            updated_at=row.updated_at or row.created_at or now,
        )

    def _mem_to_record(self, row: Dict[str, Any]) -> EnvironmentConnectionRecord:
        return EnvironmentConnectionRecord(
            id=row["id"],
            environment_id=row["environment_id"],
            name=row["name"],
            connection_type=row["connection_type"],
            purpose=row["purpose"],
            config=row.get("config") or {},
            is_default=bool(row.get("is_default")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_svc = EnvironmentConnectionService()


def list_environment_connections(
    *,
    environment_id: str,
    purpose: Optional[str] = None,
    connection_type: Optional[str] = None,
) -> List[EnvironmentConnectionRecord]:
    return _svc.list_connections(
        environment_id=environment_id, purpose=purpose, connection_type=connection_type
    )


def get_environment_connection(connection_id: UUID) -> Optional[EnvironmentConnectionRecord]:
    return _svc.get_connection(connection_id)


def get_default_environment_connection(
    environment_id: str, purpose: Purpose
) -> Optional[EnvironmentConnectionRecord]:
    return _svc.get_default_connection(environment_id, purpose)
