"""Agent discovery and listing endpoints."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from AI.src.core.registry import get_registered_agent_ids
from shared.config.agent_manifest import manifest_for_api
from shared.config.loader import get_agent_settings
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS, editable_profile_fields
from shared.config.profile_overrides import validate_profile_overrides

router = APIRouter()

AGENT_DISPLAY: Dict[str, Dict[str, str]] = {
    "dbx_cluster_tuning_agent": {
        "name": "DBX Cluster Tuning Agent",
        "description": "Per-run utilization right-sizing (Databricks cluster config).",
        "get_started_route": "/app/workspaces",
    },
}


class AgentInfo(BaseModel):
    agent_id: str
    name: str
    description: str
    get_started_route: str = "/app/workspaces"


class AgentsListResponse(BaseModel):
    agents: List[AgentInfo]


class EditableSettingsField(BaseModel):
    key: str
    label: str
    type: str
    options: List[str] | None = None
    placeholder: str | None = None
    help: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None


class EditableSettingsResponse(BaseModel):
    agent_id: str
    fields: List[EditableSettingsField]


class EffectiveSettingsPreviewRequest(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)


class EffectiveSettingsPreviewResponse(BaseModel):
    agent_id: str
    effective_settings: Dict[str, Any]


@router.get("/", response_model=AgentsListResponse)
async def list_agents():
    """List registered agents with display metadata for the UI."""
    agents: List[AgentInfo] = []
    for agent_id in get_registered_agent_ids():
        meta = AGENT_DISPLAY.get(
            agent_id,
            {
                "name": agent_id,
                "description": "Registered agent.",
                "get_started_route": "/app/workspaces",
            },
        )
        agents.append(AgentInfo(agent_id=agent_id, **meta))
    return AgentsListResponse(agents=agents)


@router.get("/{agent_id}/connection-manifest")
async def get_connection_manifest(agent_id: str):
    """Required/optional connection roles for installing this agent on a workspace."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    manifest = manifest_for_api(agent_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="No connection manifest for agent")
    return manifest


@router.get("/{agent_id}/editable-settings", response_model=EditableSettingsResponse)
async def get_editable_settings(agent_id: str):
    """Allowlisted agent_settings fields for workspace agent configuration."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    fields: List[EditableSettingsField] = []
    for f in editable_profile_fields():
        payload = {k: v for k, v in f.items() if k in EditableSettingsField.model_fields}
        fields.append(EditableSettingsField(**payload))
    return EditableSettingsResponse(agent_id=agent_id, fields=fields)


@router.post(
    "/{agent_id}/effective-settings-preview", response_model=EffectiveSettingsPreviewResponse
)
async def preview_effective_settings(agent_id: str, body: EffectiveSettingsPreviewRequest):
    """Preview merged effective settings (non-secret fields only)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    flat = validate_profile_overrides(body.overrides, allowed_fields=PROFILE_ALLOWED_FIELDS)
    settings = get_agent_settings(agent_id, overrides=flat)
    safe_keys = [
        "azure_openai_deployment_name",
        "default_model_name",
        "vector_retrieval_backend",
        "recommendation_auto_termination_minutes",
        "recommendation_cost_retry_enabled",
        "default_confidence_score",
        "guardrail_max_date_range_days",
        "use_local_data",
    ]
    effective = {k: getattr(settings, k) for k in safe_keys if hasattr(settings, k)}
    return EffectiveSettingsPreviewResponse(agent_id=agent_id, effective_settings=effective)
