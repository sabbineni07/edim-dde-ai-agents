"""Platform environment CRUD — Postgres (or in-memory when USE_POSTGRES=false)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from shared.config.environment_seed import PLATFORM_ENVIRONMENT_SEED
from shared.config.loader import get_platform_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

SourceType = Literal["databricks_uc", "local_csv"]

_MEM: Dict[str, Dict[str, Any]] = {}
_MEM_INITIALIZED = False
_SEED_CHECKED = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    raw = os.environ.get("USE_POSTGRES")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes")
    return bool(getattr(get_platform_settings(), "use_postgres", False))


@dataclass(frozen=True)
class PlatformEnvironment:
    id: str
    code: str
    display_name: str
    description: str
    environment_tier: str
    source_type: SourceType
    catalog_name: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    databricks_server_hostname: Optional[str] = None
    databricks_http_path: Optional[str] = None
    default_metrics_connection_id: Optional[str] = None
    default_llm_connection_id: Optional[str] = None
    default_dataset_id: Optional[str] = None
    sort_order: int = 0
    icon: str = "cloud"
    is_enabled: bool = True

    @property
    def table_fqn(self) -> Optional[str]:
        if self.source_type != "databricks_uc":
            return None
        parts = [p for p in (self.catalog_name, self.schema_name, self.table_name) if p]
        return ".".join(parts) if len(parts) == 3 else None

    def to_dict(
        self,
        *,
        readiness: str = "unknown",
        local_dataset: Optional[Dict[str, Any]] = None,
        is_admin: bool = False,
        metrics_connection_count: int = 0,
        metrics_dataset_count: int = 0,
        default_dataset_name: Optional[str] = None,
        default_dataset_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "code": self.code,
            "display_name": self.display_name,
            "description": self.description,
            "environment_tier": self.environment_tier,
            "source_type": self.source_type,
            "catalog_name": self.catalog_name,
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "table_fqn": self.table_fqn,
            "databricks_server_hostname": self.databricks_server_hostname,
            "databricks_http_path": self.databricks_http_path,
            "default_metrics_connection_id": self.default_metrics_connection_id,
            "default_llm_connection_id": self.default_llm_connection_id,
            "default_dataset_id": self.default_dataset_id,
            "metrics_connection_count": metrics_connection_count,
            "metrics_dataset_count": metrics_dataset_count,
            "default_dataset_name": default_dataset_name,
            "default_dataset_ref": default_dataset_ref,
            "sort_order": self.sort_order,
            "icon": self.icon,
            "is_enabled": self.is_enabled,
            "readiness": readiness,
        }
        if local_dataset is not None:
            out["local_dataset"] = local_dataset
        if is_admin:
            out["is_admin_view"] = True
        return out


def _row_to_env(row: Any) -> PlatformEnvironment:
    metrics_id = getattr(row, "default_metrics_connection_id", None)
    llm_id = getattr(row, "default_llm_connection_id", None)
    dataset_id = getattr(row, "default_dataset_id", None)
    return PlatformEnvironment(
        id=row.id,
        code=row.code,
        display_name=row.display_name,
        description=row.description or "",
        environment_tier=row.environment_tier,
        source_type=row.source_type,
        catalog_name=row.catalog_name,
        schema_name=row.schema_name,
        table_name=row.table_name,
        databricks_server_hostname=row.databricks_server_hostname,
        databricks_http_path=row.databricks_http_path,
        default_metrics_connection_id=str(metrics_id) if metrics_id else None,
        default_llm_connection_id=str(llm_id) if llm_id else None,
        default_dataset_id=str(dataset_id) if dataset_id else None,
        sort_order=int(row.sort_order or 0),
        icon=row.icon or "cloud",
        is_enabled=bool(row.is_enabled),
    )


def _mem_to_env(data: Dict[str, Any]) -> PlatformEnvironment:
    return PlatformEnvironment(
        id=data["id"],
        code=data["code"],
        display_name=data["display_name"],
        description=data.get("description") or "",
        environment_tier=data["environment_tier"],
        source_type=data["source_type"],
        catalog_name=data.get("catalog_name"),
        schema_name=data.get("schema_name"),
        table_name=data.get("table_name"),
        databricks_server_hostname=data.get("databricks_server_hostname"),
        databricks_http_path=data.get("databricks_http_path"),
        default_metrics_connection_id=data.get("default_metrics_connection_id"),
        default_llm_connection_id=data.get("default_llm_connection_id"),
        default_dataset_id=data.get("default_dataset_id"),
        sort_order=int(data.get("sort_order") or 0),
        icon=data.get("icon") or "cloud",
        is_enabled=bool(data.get("is_enabled", True)),
    )


def _init_mem_from_seed() -> None:
    global _MEM_INITIALIZED
    if _MEM_INITIALIZED:
        return
    now = _utcnow()
    for item in PLATFORM_ENVIRONMENT_SEED:
        row = dict(item)
        row.setdefault("is_enabled", True)
        row.setdefault("databricks_server_hostname", None)
        row.setdefault("databricks_http_path", None)
        row["created_at"] = now
        row["updated_at"] = now
        _MEM[row["id"]] = row
    _MEM_INITIALIZED = True


def reset_platform_environment_store_for_tests() -> None:
    """Clear in-memory store (unit tests only)."""
    global _MEM, _MEM_INITIALIZED, _SEED_CHECKED
    _MEM = {}
    _MEM_INITIALIZED = False
    _SEED_CHECKED = False


class PlatformEnvironmentService:
    def seed_if_empty(self) -> int:
        """Insert seed rows when table is empty. Postgres: once per process; mem: when store empty."""
        global _SEED_CHECKED
        if not _db_enabled():
            if _MEM_INITIALIZED:
                return len(_MEM)
            _init_mem_from_seed()
            self._seed_default_connections()
            self._seed_default_datasets()
            return len(_MEM)
        if _SEED_CHECKED:
            return 0

        from shared.database.connection import get_database_session
        from shared.database.models import PlatformEnvironmentRow

        session = get_database_session()
        try:
            count = session.query(PlatformEnvironmentRow).count()
            if count > 0:
                _SEED_CHECKED = True
                return 0
            now = _utcnow()
            for item in PLATFORM_ENVIRONMENT_SEED:
                session.add(
                    PlatformEnvironmentRow(
                        id=item["id"],
                        code=item["code"],
                        display_name=item["display_name"],
                        description=item.get("description"),
                        environment_tier=item["environment_tier"],
                        source_type=item["source_type"],
                        catalog_name=item.get("catalog_name"),
                        schema_name=item.get("schema_name"),
                        table_name=item.get("table_name"),
                        databricks_server_hostname=item.get("databricks_server_hostname"),
                        databricks_http_path=item.get("databricks_http_path"),
                        sort_order=item.get("sort_order", 0),
                        icon=item.get("icon", "cloud"),
                        is_enabled=1,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()
            logger.info("platform_environments_seeded", count=len(PLATFORM_ENVIRONMENT_SEED))
            self._seed_default_connections()
            self._seed_default_datasets()
            _SEED_CHECKED = True
            return len(PLATFORM_ENVIRONMENT_SEED)
        except Exception as e:
            session.rollback()
            logger.error("platform_environments_seed_failed", error=str(e))
            raise
        finally:
            session.close()

    def _seed_default_connections(self) -> None:
        from shared.services.environment_connection_service import (
            seed_default_connections_for_environment,
        )

        for item in PLATFORM_ENVIRONMENT_SEED:
            if item.get("source_type") != "databricks_uc":
                continue
            conn_id = seed_default_connections_for_environment(
                item["id"],
                display_name=item["display_name"],
                source_type=item["source_type"],
                seed_item=item,
            )
            if conn_id and not _db_enabled():
                row = _MEM.get(item["id"])
                if row:
                    row["default_metrics_connection_id"] = str(conn_id)
            elif conn_id and _db_enabled():
                from shared.database.connection import get_database_session
                from shared.database.models import PlatformEnvironmentRow

                session = get_database_session()
                try:
                    env_row = (
                        session.query(PlatformEnvironmentRow)
                        .filter(PlatformEnvironmentRow.id == item["id"])
                        .first()
                    )
                    if env_row and not env_row.default_metrics_connection_id:
                        env_row.default_metrics_connection_id = conn_id
                        session.commit()
                except Exception:
                    session.rollback()
                    raise
                finally:
                    session.close()

    def _seed_default_datasets(self) -> None:
        from shared.services.environment_dataset_service import (
            seed_default_datasets_for_environment,
        )

        for item in PLATFORM_ENVIRONMENT_SEED:
            source = item.get("source_type")
            if source not in ("databricks_uc", "local_csv"):
                continue
            dataset_id = seed_default_datasets_for_environment(
                item["id"],
                display_name=item["display_name"],
                source_type=source,
                seed_item=item,
            )
            if dataset_id and not _db_enabled():
                row = _MEM.get(item["id"])
                if row:
                    row["default_dataset_id"] = str(dataset_id)
            elif dataset_id and _db_enabled():
                from shared.database.connection import get_database_session
                from shared.database.models import PlatformEnvironmentRow

                session = get_database_session()
                try:
                    env_row = (
                        session.query(PlatformEnvironmentRow)
                        .filter(PlatformEnvironmentRow.id == item["id"])
                        .first()
                    )
                    if env_row and not env_row.default_dataset_id:
                        env_row.default_dataset_id = dataset_id
                        session.commit()
                except Exception:
                    session.rollback()
                    raise
                finally:
                    session.close()

    def list_environments(self, *, include_disabled: bool = False) -> List[PlatformEnvironment]:
        self.seed_if_empty()
        if not _db_enabled():
            self._seed_default_connections()
            self._seed_default_datasets()
            rows = list(_MEM.values())
            if not include_disabled:
                rows = [r for r in rows if r.get("is_enabled", True)]
            rows.sort(key=lambda r: (r.get("sort_order", 0), r.get("id", "")))
            return [_mem_to_env(r) for r in rows]

        from shared.database.connection import get_database_session
        from shared.database.models import PlatformEnvironmentRow

        session = get_database_session()
        try:
            q = session.query(PlatformEnvironmentRow)
            if not include_disabled:
                q = q.filter(PlatformEnvironmentRow.is_enabled == 1)
            rows = q.order_by(
                PlatformEnvironmentRow.sort_order.asc(),
                PlatformEnvironmentRow.id.asc(),
            ).all()
            return [_row_to_env(r) for r in rows]
        finally:
            session.close()

    def get_environment(self, environment_id: str) -> Optional[PlatformEnvironment]:
        if not _db_enabled() and not _MEM_INITIALIZED:
            self.seed_if_empty()
        eid = (environment_id or "").strip()
        if not eid:
            return None
        if not _db_enabled():
            row = _MEM.get(eid)
            return _mem_to_env(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import PlatformEnvironmentRow

        session = get_database_session()
        try:
            row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == eid)
                .first()
            )
            return _row_to_env(row) if row else None
        finally:
            session.close()

    def update_environment(self, environment_id: str, patch: Dict[str, Any]) -> PlatformEnvironment:
        env = self.get_environment(environment_id)
        if not env:
            raise ValueError(f"Environment not found: {environment_id}")

        allowed = {
            "display_name",
            "description",
            "environment_tier",
            "sort_order",
            "icon",
            "is_enabled",
        }
        updates = {k: v for k, v in patch.items() if k in allowed}

        if not _db_enabled():
            row = _MEM[environment_id]
            row.update(updates)
            row["updated_at"] = _utcnow()
            return _mem_to_env(row)

        from shared.database.connection import get_database_session
        from shared.database.models import PlatformEnvironmentRow

        session = get_database_session()
        try:
            row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == environment_id)
                .first()
            )
            if not row:
                raise ValueError(f"Environment not found: {environment_id}")
            for key, value in updates.items():
                if key == "is_enabled":
                    setattr(row, key, 1 if value else 0)
                else:
                    setattr(row, key, value)
            row.updated_at = _utcnow()
            session.commit()
            session.refresh(row)
            return _row_to_env(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_svc = PlatformEnvironmentService()


def seed_platform_environments_if_empty() -> int:
    return _svc.seed_if_empty()


def list_environments(include_disabled: bool = False) -> List[PlatformEnvironment]:
    return _svc.list_environments(include_disabled=include_disabled)


def get_environment(environment_id: str) -> Optional[PlatformEnvironment]:
    return _svc.get_environment(environment_id)


def update_environment(environment_id: str, patch: Dict[str, Any]) -> PlatformEnvironment:
    return _svc.update_environment(environment_id, patch)


def environment_settings_scope(environment_id: str) -> str:
    """Stable key for workspace_agents scoped to an environment."""
    return f"env:{environment_id}"
