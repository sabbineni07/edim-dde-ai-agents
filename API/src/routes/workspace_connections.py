"""Workspace-scoped connection CRUD."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from shared.services.workspace_connection_service import WorkspaceConnectionService

router = APIRouter()
svc = WorkspaceConnectionService()


class ConnectionCreateRequest(BaseModel):
    connection_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    config: Dict[str, Any] = Field(default_factory=dict)
    workspace_name: Optional[str] = None


class ConnectionUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    config: Optional[Dict[str, Any]] = None
    workspace_name: Optional[str] = None


class ConnectionResponse(BaseModel):
    id: str
    workspace_id: str
    workspace_name: Optional[str] = None
    connection_type: str
    name: str
    config: Dict[str, Any]
    created_at: str
    updated_at: str


@router.get("/{workspace_id}/connections", response_model=List[ConnectionResponse])
async def list_connections(
    workspace_id: str,
    connection_type: Optional[str] = Query(default=None),
):
    rows = svc.list_connections(workspace_id=workspace_id, connection_type=connection_type)
    return [ConnectionResponse(**r.to_dict()) for r in rows]


@router.post("/{workspace_id}/connections", response_model=ConnectionResponse)
async def create_connection(workspace_id: str, body: ConnectionCreateRequest):
    try:
        rec = svc.create_connection(
            workspace_id=workspace_id,
            workspace_name=body.workspace_name,
            connection_type=body.connection_type,
            name=body.name,
            config=body.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ConnectionResponse(**rec.to_dict())


@router.get("/{workspace_id}/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(workspace_id: str, connection_id: UUID):
    rec = svc.get_connection(connection_id)
    if not rec or rec.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionResponse(**rec.to_dict())


@router.put("/{workspace_id}/connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(workspace_id: str, connection_id: UUID, body: ConnectionUpdateRequest):
    existing = svc.get_connection(connection_id)
    if not existing or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        rec = svc.update_connection(
            connection_id,
            name=body.name,
            config=body.config,
            workspace_name=body.workspace_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not rec:
        raise HTTPException(status_code=404, detail="Connection not found")
    return ConnectionResponse(**rec.to_dict())


@router.delete("/{workspace_id}/connections/{connection_id}")
async def delete_connection(workspace_id: str, connection_id: UUID):
    existing = svc.get_connection(connection_id)
    if not existing or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Connection not found")
    ok = svc.delete_connection(connection_id)
    return {"deleted": ok}
