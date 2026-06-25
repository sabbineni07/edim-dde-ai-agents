"""Environment-scoped connection CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from shared.auth.admin import is_admin
from shared.config.connection_types import purpose_for_connection_type
from shared.services.environment_connection_service import EnvironmentConnectionService
from shared.services.platform_environment_service import get_environment

router = APIRouter()
svc = EnvironmentConnectionService()

Purpose = Literal["metrics", "llm", "rag"]


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


class ConnectionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    connection_type: str = Field(..., min_length=1)
    purpose: Optional[Purpose] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    set_default: bool = False


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    config: Optional[Dict[str, Any]] = None


class ConnectionResponse(BaseModel):
    id: str
    environment_id: str
    name: str
    connection_type: str
    purpose: str
    config: Dict[str, Any]
    is_default: bool
    created_at: str
    updated_at: str


@router.get("/{environment_id}/connections", response_model=List[ConnectionResponse])
async def list_connections(
    environment_id: str,
    purpose: Optional[str] = Query(default=None),
    connection_type: Optional[str] = Query(default=None),
):
    _require_env(environment_id)
    rows = svc.list_connections(
        environment_id=environment_id,
        purpose=purpose,
        connection_type=connection_type,
    )
    return [ConnectionResponse(**r.to_dict()) for r in rows]


@router.post("/{environment_id}/connections", response_model=ConnectionResponse)
async def create_connection(
    environment_id: str,
    body: ConnectionCreateRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    try:
        purpose = body.purpose or purpose_for_connection_type(body.connection_type)
        rec = svc.create_connection(
            environment_id=environment_id,
            name=body.name,
            connection_type=body.connection_type,
            purpose=purpose,
            config=body.config,
            set_default=body.set_default,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ConnectionResponse(**rec.to_dict())


@router.get("/{environment_id}/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(environment_id: str, connection_id: UUID):
    _require_env(environment_id)
    rec = svc.get_connection(connection_id)
    if not rec or rec.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionResponse(**rec.to_dict())


@router.put("/{environment_id}/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    environment_id: str,
    connection_id: UUID,
    body: ConnectionUpdateRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_connection(connection_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        rec = svc.update_connection(connection_id, name=body.name, config=body.config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not rec:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionResponse(**rec.to_dict())


@router.delete("/{environment_id}/connections/{connection_id}")
async def delete_connection(
    environment_id: str,
    connection_id: UUID,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_connection(connection_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    ok = svc.delete_connection(connection_id)
    return {"deleted": ok}


@router.post(
    "/{environment_id}/connections/{connection_id}/set-default", response_model=ConnectionResponse
)
async def set_default_connection(
    environment_id: str,
    connection_id: UUID,
    purpose: Optional[Purpose] = Query(default=None),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    _require_admin(x_user_name, x_user_id)
    _require_env(environment_id)
    existing = svc.get_connection(connection_id)
    if not existing or existing.environment_id != environment_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    resolved_purpose = purpose or purpose_for_connection_type(existing.connection_type)
    try:
        rec = svc.set_default(connection_id, purpose=resolved_purpose)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ConnectionResponse(**rec.to_dict())
