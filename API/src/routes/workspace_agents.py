"""Workspace-scoped agent installs (bindings to environment connections)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from shared.services.workspace_agent_service import WorkspaceAgentService

router = APIRouter()
svc = WorkspaceAgentService()


class WorkspaceAgentCreateRequest(BaseModel):
    environment_id: str = Field(
        ..., min_length=1, description="Platform environment for connection bindings"
    )
    agent_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    bindings: Dict[str, Any] = Field(default_factory=dict)
    agent_settings: Dict[str, Any] = Field(default_factory=dict)
    workspace_name: Optional[str] = None


class WorkspaceAgentUpdateRequest(BaseModel):
    environment_id: str = Field(
        ..., min_length=1, description="Platform environment for connection bindings"
    )
    name: Optional[str] = Field(default=None, min_length=1)
    bindings: Optional[Dict[str, Any]] = None
    agent_settings: Optional[Dict[str, Any]] = None
    workspace_name: Optional[str] = None


class WorkspaceAgentResponse(BaseModel):
    id: str
    workspace_id: str
    workspace_name: Optional[str] = None
    agent_id: str
    name: str
    bindings: Dict[str, Any]
    agent_settings: Dict[str, Any]
    created_at: str
    updated_at: str


@router.get("/{workspace_id}/agents", response_model=List[WorkspaceAgentResponse])
async def list_workspace_agents(
    workspace_id: str,
    agent_id: Optional[str] = Query(default=None),
):
    rows = svc.list_agents(workspace_id=workspace_id, agent_id=agent_id)
    return [WorkspaceAgentResponse(**r.to_dict()) for r in rows]


@router.post("/{workspace_id}/agents", response_model=WorkspaceAgentResponse)
async def create_workspace_agent(workspace_id: str, body: WorkspaceAgentCreateRequest):
    try:
        rec = svc.create_agent(
            environment_id=body.environment_id,
            workspace_id=workspace_id,
            workspace_name=body.workspace_name,
            agent_id=body.agent_id,
            name=body.name,
            bindings=body.bindings,
            agent_settings=body.agent_settings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return WorkspaceAgentResponse(**rec.to_dict())


@router.get("/{workspace_id}/agents/{workspace_agent_id}", response_model=WorkspaceAgentResponse)
async def get_workspace_agent(workspace_id: str, workspace_agent_id: UUID):
    rec = svc.get_agent(workspace_agent_id)
    if not rec or rec.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace agent not found")
    return WorkspaceAgentResponse(**rec.to_dict())


@router.put("/{workspace_id}/agents/{workspace_agent_id}", response_model=WorkspaceAgentResponse)
async def update_workspace_agent(
    workspace_id: str,
    workspace_agent_id: UUID,
    body: WorkspaceAgentUpdateRequest,
):
    existing = svc.get_agent(workspace_agent_id)
    if not existing or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace agent not found")
    try:
        rec = svc.update_agent(
            workspace_agent_id,
            environment_id=body.environment_id,
            name=body.name,
            bindings=body.bindings,
            agent_settings=body.agent_settings,
            workspace_name=body.workspace_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not rec:
        raise HTTPException(status_code=404, detail="Workspace agent not found")
    return WorkspaceAgentResponse(**rec.to_dict())


@router.delete("/{workspace_id}/agents/{workspace_agent_id}")
async def delete_workspace_agent(workspace_id: str, workspace_agent_id: UUID):
    existing = svc.get_agent(workspace_agent_id)
    if not existing or existing.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Workspace agent not found")
    ok = svc.delete_agent(workspace_agent_id)
    return {"deleted": ok}
