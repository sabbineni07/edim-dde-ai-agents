"""Environment-scoped dataset (data product) CRUD."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from shared.config.dataset_profiles import validate_dataset_fields
from shared.config.loader import get_platform_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_MEM_DATASETS: Dict[UUID, Dict[str, Any]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_enabled() -> bool:
    raw = os.environ.get("USE_POSTGRES")
    if raw is not None:
        return raw.strip().lower() in ("1", "true", "yes")
    return bool(getattr(get_platform_settings(), "use_postgres", False))


def reset_environment_dataset_store_for_tests() -> None:
    """Clear in-memory datasets (unit tests only)."""
    global _MEM_DATASETS
    _MEM_DATASETS = {}


@dataclass(frozen=True)
class EnvironmentDatasetRecord:
    id: UUID
    environment_id: str
    name: str
    description: Optional[str]
    source_type: str
    table_fqn: Optional[str]
    local_path: Optional[str]
    schema_profile: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @property
    def table_ref(self) -> Optional[str]:
        if self.source_type == "databricks_delta":
            return (self.table_fqn or "").strip() or None
        if self.source_type == "local_csv":
            return (self.local_path or "").strip() or None
        return None

    def to_dict(self) -> Dict[str, Any]:
        created = self.created_at or _utcnow()
        updated = self.updated_at or created
        return {
            "id": str(self.id),
            "environment_id": self.environment_id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type,
            "table_fqn": self.table_fqn,
            "local_path": self.local_path,
            "schema_profile": self.schema_profile,
            "is_default": self.is_default,
            "table_ref": self.table_ref,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        }


def _table_fqn_from_seed_item(item: Dict[str, Any]) -> str:
    parts = [item.get("catalog_name"), item.get("schema_name"), item.get("table_name")]
    if all(parts):
        return ".".join(str(p) for p in parts)
    return ""


def seed_default_datasets_for_environment(
    environment_id: str,
    *,
    display_name: str,
    source_type: str,
    seed_item: Optional[Dict[str, Any]] = None,
) -> Optional[UUID]:
    """Create default metrics dataset when missing."""
    svc = EnvironmentDatasetService()
    existing = svc.list_datasets(environment_id=environment_id)
    if existing:
        default = next((d for d in existing if d.is_default), existing[0])
        return default.id

    item = seed_item or {}
    if source_type == "databricks_uc":
        table_fqn = _table_fqn_from_seed_item(item)
        if not table_fqn:
            return None
        rec = svc.create_dataset(
            environment_id=environment_id,
            name="Job cluster metrics",
            description=f"Default {display_name} metrics table",
            source_type="databricks_delta",
            schema_profile="job_cluster_metrics",
            table_fqn=table_fqn,
            set_default=True,
        )
        return rec.id

    if source_type == "local_csv":
        from shared.services.local_dataset_service import resolve_fallback_path

        rec = svc.create_dataset(
            environment_id=environment_id,
            name="Sample job metrics",
            description="Bundled sample CSV for local development",
            source_type="local_csv",
            schema_profile="job_cluster_metrics",
            local_path=str(resolve_fallback_path()),
            set_default=True,
        )
        return rec.id

    return None


def _sync_mem_default_dataset_id(environment_id: str, dataset_id: Optional[UUID]) -> None:
    if _db_enabled():
        return
    from shared.services.platform_environment_service import _MEM

    row = _MEM.get(environment_id)
    if row is not None:
        row["default_dataset_id"] = str(dataset_id) if dataset_id else None


class EnvironmentDatasetService:
    def list_datasets(
        self,
        *,
        environment_id: str,
        schema_profile: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> List[EnvironmentDatasetRecord]:
        eid = (environment_id or "").strip()
        if not eid:
            return []

        if not _db_enabled():
            rows = [r for r in _MEM_DATASETS.values() if r["environment_id"] == eid]
            if schema_profile:
                rows = [r for r in rows if r["schema_profile"] == schema_profile]
            if source_type:
                rows = [r for r in rows if r["source_type"] == source_type]
            return [
                self._mem_to_record(r)
                for r in sorted(rows, key=lambda x: (not x.get("is_default"), x["name"]))
            ]

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow

        session = get_database_session()
        try:
            q = session.query(EnvironmentDatasetRow).filter(
                EnvironmentDatasetRow.environment_id == eid
            )
            if schema_profile:
                q = q.filter(EnvironmentDatasetRow.schema_profile == schema_profile)
            if source_type:
                q = q.filter(EnvironmentDatasetRow.source_type == source_type)
            rows = q.order_by(
                EnvironmentDatasetRow.is_default.desc(),
                EnvironmentDatasetRow.name.asc(),
            ).all()
            return [self._row_to_record(r) for r in rows]
        finally:
            session.close()

    def get_dataset(self, dataset_id: UUID) -> Optional[EnvironmentDatasetRecord]:
        if not _db_enabled():
            row = _MEM_DATASETS.get(dataset_id)
            return self._mem_to_record(row) if row else None

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentDatasetRow)
                .filter(EnvironmentDatasetRow.id == dataset_id)
                .first()
            )
            return self._row_to_record(row) if row else None
        finally:
            session.close()

    def get_default_dataset(self, environment_id: str) -> Optional[EnvironmentDatasetRecord]:
        rows = self.list_datasets(environment_id=environment_id)
        return next((r for r in rows if r.is_default), rows[0] if rows else None)

    def create_dataset(
        self,
        *,
        environment_id: str,
        name: str,
        description: Optional[str] = None,
        source_type: str,
        schema_profile: str,
        table_fqn: Optional[str] = None,
        local_path: Optional[str] = None,
        set_default: bool = False,
    ) -> EnvironmentDatasetRecord:
        clean = validate_dataset_fields(
            source_type=source_type,
            schema_profile=schema_profile,
            table_fqn=table_fqn,
            local_path=local_path,
        )

        if not _db_enabled():
            now = _utcnow()
            did = uuid4()
            if set_default:
                self._clear_default_mem(environment_id)
            _MEM_DATASETS[did] = {
                "id": did,
                "environment_id": environment_id,
                "name": name,
                "description": description,
                "source_type": clean["source_type"],
                "table_fqn": clean["table_fqn"],
                "local_path": clean["local_path"],
                "schema_profile": clean["schema_profile"],
                "is_default": set_default,
                "created_at": now,
                "updated_at": now,
            }
            if set_default:
                _sync_mem_default_dataset_id(environment_id, did)
            return self._mem_to_record(_MEM_DATASETS[did])

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            if set_default:
                session.query(EnvironmentDatasetRow).filter(
                    EnvironmentDatasetRow.environment_id == environment_id,
                    EnvironmentDatasetRow.is_default.is_(True),
                ).update({"is_default": False})

            row = EnvironmentDatasetRow(
                environment_id=environment_id,
                name=name,
                description=description,
                source_type=clean["source_type"],
                table_fqn=clean["table_fqn"],
                local_path=clean["local_path"],
                schema_profile=clean["schema_profile"],
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
                    env_row.default_dataset_id = row.id

            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_dataset(
        self,
        dataset_id: UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        table_fqn: Optional[str] = None,
        local_path: Optional[str] = None,
    ) -> Optional[EnvironmentDatasetRecord]:
        existing = self.get_dataset(dataset_id)
        if not existing:
            return None

        new_name = name if name is not None else existing.name
        new_desc = description if description is not None else existing.description
        new_table = table_fqn if table_fqn is not None else existing.table_fqn
        new_path = local_path if local_path is not None else existing.local_path
        clean = validate_dataset_fields(
            source_type=existing.source_type,
            schema_profile=existing.schema_profile,
            table_fqn=new_table,
            local_path=new_path,
        )

        if not _db_enabled():
            row = _MEM_DATASETS.get(dataset_id)
            if not row:
                return None
            row["name"] = new_name
            row["description"] = new_desc
            row["table_fqn"] = clean["table_fqn"]
            row["local_path"] = clean["local_path"]
            row["updated_at"] = _utcnow()
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentDatasetRow)
                .filter(EnvironmentDatasetRow.id == dataset_id)
                .first()
            )
            if not row:
                return None
            row.name = new_name
            row.description = new_desc
            row.table_fqn = clean["table_fqn"]
            row.local_path = clean["local_path"]
            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_dataset(self, dataset_id: UUID) -> bool:
        existing = self.get_dataset(dataset_id)
        if not existing:
            return False

        if not _db_enabled():
            row = _MEM_DATASETS.pop(dataset_id, None)
            if row and row.get("is_default"):
                _sync_mem_default_dataset_id(row["environment_id"], None)
            return row is not None

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            row = (
                session.query(EnvironmentDatasetRow)
                .filter(EnvironmentDatasetRow.id == dataset_id)
                .first()
            )
            if not row:
                return False

            env_row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == row.environment_id)
                .first()
            )
            if env_row and env_row.default_dataset_id == row.id:
                env_row.default_dataset_id = None

            session.delete(row)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_default(self, dataset_id: UUID) -> EnvironmentDatasetRecord:
        rec = self.get_dataset(dataset_id)
        if not rec:
            raise ValueError("Dataset not found")

        if not _db_enabled():
            self._clear_default_mem(rec.environment_id)
            row = _MEM_DATASETS[dataset_id]
            row["is_default"] = True
            row["updated_at"] = _utcnow()
            _sync_mem_default_dataset_id(rec.environment_id, dataset_id)
            return self._mem_to_record(row)

        from shared.database.connection import get_database_session
        from shared.database.models import EnvironmentDatasetRow, PlatformEnvironmentRow

        session = get_database_session()
        try:
            session.query(EnvironmentDatasetRow).filter(
                EnvironmentDatasetRow.environment_id == rec.environment_id,
                EnvironmentDatasetRow.is_default.is_(True),
            ).update({"is_default": False})

            row = (
                session.query(EnvironmentDatasetRow)
                .filter(EnvironmentDatasetRow.id == dataset_id)
                .first()
            )
            if not row:
                raise ValueError("Dataset not found")
            row.is_default = True

            env_row = (
                session.query(PlatformEnvironmentRow)
                .filter(PlatformEnvironmentRow.id == rec.environment_id)
                .first()
            )
            if env_row:
                env_row.default_dataset_id = row.id

            session.commit()
            session.refresh(row)
            return self._row_to_record(row)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _clear_default_mem(self, environment_id: str) -> None:
        for row in _MEM_DATASETS.values():
            if row["environment_id"] == environment_id:
                row["is_default"] = False

    def _row_to_record(self, row) -> EnvironmentDatasetRecord:
        now = _utcnow()
        return EnvironmentDatasetRecord(
            id=row.id,
            environment_id=row.environment_id,
            name=row.name,
            description=getattr(row, "description", None),
            source_type=row.source_type,
            table_fqn=row.table_fqn,
            local_path=row.local_path,
            schema_profile=row.schema_profile,
            is_default=bool(row.is_default),
            created_at=row.created_at or now,
            updated_at=row.updated_at or row.created_at or now,
        )

    def _mem_to_record(self, row: Dict[str, Any]) -> EnvironmentDatasetRecord:
        return EnvironmentDatasetRecord(
            id=row["id"],
            environment_id=row["environment_id"],
            name=row["name"],
            description=row.get("description"),
            source_type=row["source_type"],
            table_fqn=row.get("table_fqn"),
            local_path=row.get("local_path"),
            schema_profile=row["schema_profile"],
            is_default=bool(row.get("is_default")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def get_environment_dataset(dataset_id: UUID) -> Optional[EnvironmentDatasetRecord]:
    return EnvironmentDatasetService().get_dataset(dataset_id)


def get_default_environment_dataset(environment_id: str) -> Optional[EnvironmentDatasetRecord]:
    return EnvironmentDatasetService().get_default_dataset(environment_id)
