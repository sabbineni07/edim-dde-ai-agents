"""Agent discovery and listing endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from AI.src.core.registry import get_registered_agent_ids
from shared.auth.admin import is_admin
from shared.config.agent_manifest import manifest_for_api
from shared.config.loader import get_agent_settings
from shared.config.profile_field_meta import PROFILE_ALLOWED_FIELDS, editable_profile_fields
from shared.config.profile_overrides import validate_profile_overrides
from shared.services.agent_content_service import (
    diff_agent_prompt_versions,
    diff_agent_skill_versions,
    get_agent_content,
    list_agent_prompt_versions,
    list_agent_skill_versions,
    reset_agent_content_to_seed,
    seed_agent_content_if_empty,
    update_agent_prompt,
    update_agent_skill,
)

router = APIRouter()

AGENT_DISPLAY: Dict[str, Dict[str, str]] = {
    "dbx_cluster_tuning_agent": {
        "name": "DBX Cluster Tuning Agent",
        "description": "Per-run utilization right-sizing (Databricks cluster config).",
        "get_started_route": "/app/environments",
    },
}


class AgentInfo(BaseModel):
    agent_id: str
    name: str
    description: str
    get_started_route: str = "/app/environments"


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
    group: str | None = None


class EditableSettingsResponse(BaseModel):
    agent_id: str
    fields: List[EditableSettingsField]


class EffectiveSettingsPreviewRequest(BaseModel):
    overrides: Dict[str, Any] = Field(default_factory=dict)


class EffectiveSettingsPreviewResponse(BaseModel):
    agent_id: str
    effective_settings: Dict[str, Any]


class AgentDefinitionContent(BaseModel):
    agent_id: str
    display_name: str
    description: str | None = None
    version: int = 1
    is_enabled: bool = True
    get_started_route: str = "/app/environments"
    updated_at: str | None = None


class AgentPromptContent(BaseModel):
    chain_name: str
    role: str
    content: str
    version: int = 1
    sort_order: int = 0
    updated_at: str | None = None
    updated_by: str | None = None
    usage_summary: str | None = None
    usage_detail: str | None = None
    backend_ref: str | None = None


class AgentSkillContent(BaseModel):
    skill_key: str
    title: str
    description: str | None = None
    content: str
    version: int = 1
    sort_order: int = 0
    updated_at: str | None = None
    updated_by: str | None = None
    usage_summary: str | None = None
    usage_detail: str | None = None
    backend_ref: str | None = None


class AgentChainUsage(BaseModel):
    summary: str
    detail: str
    backend_ref: str | None = None


class AgentContentResponse(BaseModel):
    agent_id: str
    definition: AgentDefinitionContent
    prompts: List[AgentPromptContent]
    skills: List[AgentSkillContent]
    source: str
    chain_usage: Dict[str, AgentChainUsage] = Field(default_factory=dict)
    can_edit: bool = False


class UpdatePromptRequest(BaseModel):
    content: str = Field(..., min_length=1)


class UpdateSkillRequest(BaseModel):
    content: str = Field(..., min_length=1)
    title: Optional[str] = None
    description: Optional[str] = None


class AgentContentVersionSummary(BaseModel):
    version: int
    is_active: bool = False
    updated_at: str | None = None
    updated_by: str | None = None
    content_length: int = 0


class AgentContentVersionListResponse(BaseModel):
    agent_id: str
    kind: str
    chain_name: str | None = None
    role: str | None = None
    skill_key: str | None = None
    versions: List[AgentContentVersionSummary]


class AgentContentDiffResponse(BaseModel):
    agent_id: str
    kind: str
    chain_name: str | None = None
    role: str | None = None
    skill_key: str | None = None
    from_version: int
    to_version: int
    diff: str
    has_changes: bool = True


class AgentContentResetResponse(BaseModel):
    agent_id: str
    prompts_reset: int
    skills_reset: int
    content: AgentContentResponse


def _user_id(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    return (x_user_id or x_user_name or "anonymous").strip() or "anonymous"


def _require_admin(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    user = _user_id(x_user_name, x_user_id)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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
                "get_started_route": "/app/environments",
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
        "llm_temperature",
        "llm_top_p",
        "sizing_llm_temperature",
        "sizing_llm_top_p",
        "explanation_llm_temperature",
        "explanation_llm_top_p",
        "rag_top_k_recommendations",
        "rag_top_k_jobs",
        "use_local_data",
    ]
    effective = {k: getattr(settings, k) for k in safe_keys if hasattr(settings, k)}
    return EffectiveSettingsPreviewResponse(agent_id=agent_id, effective_settings=effective)


@router.get("/{agent_id}/content", response_model=AgentContentResponse)
async def get_agent_content_endpoint(
    agent_id: str,
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """Prompts and skills for an agent."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    seed_agent_content_if_empty()
    bundle = get_agent_content(agent_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Agent content not found")
    user = (x_user_name or "").strip()
    payload = bundle.to_dict(can_edit=is_admin(user))
    return AgentContentResponse(**payload)


@router.put("/{agent_id}/prompts/{chain_name}/{role}", response_model=AgentPromptContent)
async def update_agent_prompt_endpoint(
    agent_id: str,
    chain_name: str,
    role: str,
    body: UpdatePromptRequest,
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Update an active prompt template (admin only)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    user = _require_admin(x_user_name, x_user_id)
    seed_agent_content_if_empty()
    try:
        updated = update_agent_prompt(
            agent_id,
            chain_name,
            role,
            body.content,
            updated_by=user,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentPromptContent(**updated)


@router.put("/{agent_id}/skills/{skill_key}", response_model=AgentSkillContent)
async def update_agent_skill_endpoint(
    agent_id: str,
    skill_key: str,
    body: UpdateSkillRequest,
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Update an active skill block (admin only)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    user = _require_admin(x_user_name, x_user_id)
    seed_agent_content_if_empty()
    try:
        updated = update_agent_skill(
            agent_id,
            skill_key,
            content=body.content,
            updated_by=user,
            title=body.title,
            description=body.description,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Skill not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentSkillContent(**updated)


@router.get(
    "/{agent_id}/prompts/{chain_name}/{role}/versions",
    response_model=AgentContentVersionListResponse,
)
async def list_prompt_versions_endpoint(agent_id: str, chain_name: str, role: str):
    """List saved versions for a prompt (newest first)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    seed_agent_content_if_empty()
    try:
        versions = list_agent_prompt_versions(agent_id, chain_name, role)
    except KeyError:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if not versions:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return AgentContentVersionListResponse(
        agent_id=agent_id,
        kind="prompt",
        chain_name=chain_name,
        role=role,
        versions=[AgentContentVersionSummary(**v) for v in versions],
    )


@router.get(
    "/{agent_id}/skills/{skill_key}/versions",
    response_model=AgentContentVersionListResponse,
)
async def list_skill_versions_endpoint(agent_id: str, skill_key: str):
    """List saved versions for a skill (newest first)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    seed_agent_content_if_empty()
    versions = list_agent_skill_versions(agent_id, skill_key)
    if not versions:
        raise HTTPException(status_code=404, detail="Skill not found")
    return AgentContentVersionListResponse(
        agent_id=agent_id,
        kind="skill",
        skill_key=skill_key,
        versions=[AgentContentVersionSummary(**v) for v in versions],
    )


@router.get(
    "/{agent_id}/prompts/{chain_name}/{role}/diff",
    response_model=AgentContentDiffResponse,
)
async def diff_prompt_versions_endpoint(
    agent_id: str,
    chain_name: str,
    role: str,
    from_version: int,
    to_version: int,
):
    """Unified diff between two prompt versions."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    seed_agent_content_if_empty()
    try:
        payload = diff_agent_prompt_versions(
            agent_id,
            chain_name,
            role,
            from_version=from_version,
            to_version=to_version,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Version not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentContentDiffResponse(
        agent_id=agent_id,
        kind="prompt",
        chain_name=chain_name,
        role=role,
        **payload,
    )


@router.get(
    "/{agent_id}/skills/{skill_key}/diff",
    response_model=AgentContentDiffResponse,
)
async def diff_skill_versions_endpoint(
    agent_id: str,
    skill_key: str,
    from_version: int,
    to_version: int,
):
    """Unified diff between two skill versions."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    seed_agent_content_if_empty()
    try:
        payload = diff_agent_skill_versions(
            agent_id,
            skill_key,
            from_version=from_version,
            to_version=to_version,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Version not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return AgentContentDiffResponse(
        agent_id=agent_id,
        kind="skill",
        skill_key=skill_key,
        **payload,
    )


@router.post("/{agent_id}/content/reset", response_model=AgentContentResetResponse)
async def reset_agent_content_endpoint(
    agent_id: str,
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    """Restore all prompts and skills to seed defaults (admin only)."""
    if agent_id not in get_registered_agent_ids():
        raise HTTPException(status_code=404, detail="Agent not found")
    user = _require_admin(x_user_name, x_user_id)
    seed_agent_content_if_empty()
    try:
        result = reset_agent_content_to_seed(agent_id, updated_by=user)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return AgentContentResetResponse(
        agent_id=result["agent_id"],
        prompts_reset=result["prompts_reset"],
        skills_reset=result["skills_reset"],
        content=AgentContentResponse(**result["content"]),
    )
