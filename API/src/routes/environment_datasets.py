"""Environment-scoped dataset CRUD."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from shared.auth.admin import is_admin
from shared.services.environment_dataset_service import EnvironmentDatasetService
from shared.services.platform_environment_service import get_environment

router = APIRouter()
svc = EnvironmentDatasetService()


def _user_id(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    return (x_user_id or x_user_name or "anonymous").strip() or "anonymous"


def _require_admin(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    user = _user_id(x_user_name, x_user_id)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _require_env(environment_id: str):
    env = get_environment(environment_id)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    return env


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    source_type: str = Field(..., min_length=1)
    schema_profile: str = Field(..., min_length=1)
    table_fqn: Optional[str] = None
    local_path: Optional[str] = None
    set_default: bool = False


class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    table_fqn: Optional[str] = None
    local_path: Optional[str] = None


class DatasetResponse(BaseModel):
    id: str
    environment_id: str
    name: str
    description: Optional[str] = None
    source_type: str
    table_fqn: Optional[str] = None
    local_path: Optional[str] = None
    schema_profile: str
    is_default: bool
    table_ref: Optional[str] = None
    created_at: str
    updated_at: str


@router.get("/{environment_id}/datasets", response_model=List[DatasetResponse])
async def list_datasets(
    environment_id: str,
    schema_profile: Optional[str] = Query(default=None),
    source_type: Optional[str] = Query(default=None),
):
    _require_env(environment_id)
    rows = svc.list_datasets(
        environment_id=environment_id,
        schema_profile=schema_profile,
        source_type=source_type,
    )
    return [DatasetResponse(**r.to_dict()) for r in rows]


@router.post("/{environment_id}/datasets", response_model=DatasetResponse)
async def create_dataset(
    environment_id: str,
    body: DatasetCreateRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    try:
        rec = svc.create_dataset(
            environment_id=environment_id,
            name=body.name,
            description=body.description,
            source_type=body.source_type,
            schema_profile=body.schema_profile,
            table_fqn=body.table_fqn,
            local_path=body.local_path,
            set_default=body.set_default,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DatasetResponse(**rec.to_dict())


@router.get("/{environment_id}/datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(environment_id: str, dataset_id: UUID):
    _require_env(environment_id)
    rec = svc.get_dataset(dataset_id)
    if not rec or rec.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetResponse(**rec.to_dict())


@router.put("/{environment_id}/datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    environment_id: str,
    dataset_id: UUID,
    body: DatasetUpdateRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_dataset(dataset_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        rec = svc.update_dataset(
            dataset_id,
            name=body.name,
            description=body.description,
            table_fqn=body.table_fqn,
            local_path=body.local_path,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not rec:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetResponse(**rec.to_dict())


@router.delete("/{environment_id}/datasets/{dataset_id}")
async def delete_dataset(
    environment_id: str,
    dataset_id: UUID,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_dataset(dataset_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    ok = svc.delete_dataset(dataset_id)
    return {"deleted": ok}


@router.post(
    "/{environment_id}/datasets/{dataset_id}/set-default",
    response_model=DatasetResponse,
)
async def set_default_dataset(
    environment_id: str,
    dataset_id: UUID,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_dataset(dataset_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    try:
        rec = svc.set_default(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return DatasetResponse(**rec.to_dict())
