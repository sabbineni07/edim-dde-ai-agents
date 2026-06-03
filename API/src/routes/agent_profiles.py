"""Agent profile CRUD endpoints."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS
from shared.config.profile_overrides import validate_profile_overrides
from shared.services.agent_profile_service import AgentProfileService

router = APIRouter()
svc = AgentProfileService()


class AgentProfileCreateRequest(BaseModel):
    agent_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    overrides: Dict[str, Any] = Field(default_factory=dict)


class AgentProfileUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    overrides: Optional[Dict[str, Any]] = None


class AgentProfileResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    overrides: Dict[str, Any]
    created_at: str
    updated_at: str


@router.get("/", response_model=list[AgentProfileResponse])
async def list_agent_profiles(agent_id: Optional[str] = Query(default=None)):
    profiles = svc.list_profiles(agent_id=agent_id)
    return [AgentProfileResponse(**p.to_dict()) for p in profiles]


@router.get("/{profile_id}", response_model=AgentProfileResponse)
async def get_agent_profile(profile_id: UUID):
    prof = svc.get_profile(profile_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return AgentProfileResponse(**prof.to_dict())


@router.post("/", response_model=AgentProfileResponse)
async def create_agent_profile(req: AgentProfileCreateRequest):
    flat = validate_profile_overrides(req.overrides, allowed_fields=PROFILE_ALLOWED_FIELDS)
    prof = svc.create_profile(agent_id=req.agent_id, name=req.name, overrides=flat)
    return AgentProfileResponse(**prof.to_dict())


@router.put("/{profile_id}", response_model=AgentProfileResponse)
async def update_agent_profile(profile_id: UUID, req: AgentProfileUpdateRequest):
    flat = None
    if req.overrides is not None:
        flat = validate_profile_overrides(req.overrides, allowed_fields=PROFILE_ALLOWED_FIELDS)
    prof = svc.update_profile(profile_id, name=req.name, overrides=flat)
    if not prof:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return AgentProfileResponse(**prof.to_dict())


@router.delete("/{profile_id}")
async def delete_agent_profile(profile_id: UUID):
    ok = svc.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent profile not found")
    return {"deleted": True}
