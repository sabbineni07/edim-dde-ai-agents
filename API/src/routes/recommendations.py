"""Recommendation endpoints."""

import time
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from AI.src.services.azure_openai_service import AzureOpenAINotConfiguredError
from API.src.deps import get_agent, get_cost_logger
from shared.config.loader import get_agent_settings
from shared.guardrails import NoJobMetricsError, validate_intent, validate_recommendation_request
from shared.recommendation_lifecycle import (
    ALLOWED_TRANSITIONS,
    LIFECYCLE_DISPLAY_LABELS,
    InvalidLifecycleTransitionError,
    allowed_next_statuses,
    lifecycle_display_label,
    normalize_lifecycle_status,
)
from shared.services.agent_profile_service import AgentProfileService
from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService
from shared.services.workspace_agent_service import WorkspaceAgentService
from shared.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

SUPPORTED_INTENT = "cluster_recommendation"


class GenerateRecommendationRequest(BaseModel):
    """Request model for per-job-run cluster recommendations."""

    agent_id: str = Field(
        default="job_run_cluster_sizing",
        description="Which agent to run (default: job_run_cluster_sizing).",
    )
    profile_id: Optional[str] = Field(
        default=None,
        description="Optional agent profile id (UUID) to apply as settings overrides (legacy).",
    )
    workspace_agent_id: Optional[str] = Field(
        default=None,
        description="Workspace agent install id (UUID); resolves connection bindings (preferred).",
    )
    job_id: str = Field(..., min_length=1, description="Databricks job ID")
    job_run_id: str = Field(..., min_length=1, description="Databricks job run ID")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    include_explanation: bool = Field(
        default=False,
        description="If true, run explanation LLM chain (slower). Default false for UI on-demand.",
    )
    job_run_ingest: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional precomputed run metrics (Copilot-style flat JSON). Skips collector when set.",
    )
    intent: Optional[str] = Field(
        default=SUPPORTED_INTENT,
        description="Request intent; only 'cluster_recommendation' is supported.",
    )


class RecommendationResponse(BaseModel):
    """Response model for recommendations."""

    request_id: Optional[str] = None
    job_run_id: Optional[str] = None
    current_configuration: Optional[Dict] = None
    recommendation: Dict
    explanation: str = ""
    pattern_analysis: str = ""
    risk_assessment: Dict = Field(default_factory=dict)
    reason_codes: list = Field(default_factory=list)
    job_run_ingest: Optional[Dict] = None
    sizing_hints: Optional[Dict] = None
    llm_recommendation: Optional[Dict] = None
    guardrail_recommendation: Optional[Dict] = None
    guardrail_adjustments: list = Field(default_factory=list)
    recommendation_attempts: int = 1
    comparison: Optional[Dict] = None
    token_usage_analysis: Optional[Dict] = None


class LifecycleMetaResponse(BaseModel):
    statuses: List[str]
    display_labels: Dict[str, str]
    allowed_transitions: Dict[str, List[str]]


class LifecycleTransitionRequest(BaseModel):
    status: str = Field(..., description="Target lifecycle status")
    changed_by: Optional[str] = Field(
        default=None,
        min_length=1,
        description="User id or email making the change (optional if X-User-Name header is set)",
    )
    notes: Optional[str] = Field(default=None, max_length=2000)


class LifecycleEventResponse(BaseModel):
    id: Optional[int] = None
    request_id: str
    from_status: Optional[str] = None
    to_status: str
    changed_by: str
    changed_at: Optional[str] = None
    notes: Optional[str] = None


class LifecycleTransitionResponse(BaseModel):
    request_id: str
    lifecycle_status: str
    lifecycle_status_label: str
    lifecycle_updated_at: str
    lifecycle_updated_by: str
    allowed_next_statuses: List[str]
    event: LifecycleEventResponse


@router.get("/lifecycle/meta", response_model=LifecycleMetaResponse)
async def get_lifecycle_meta():
    """Lifecycle states and allowed transitions for UI."""
    return LifecycleMetaResponse(
        statuses=sorted(LIFECYCLE_DISPLAY_LABELS.keys()),
        display_labels=dict(LIFECYCLE_DISPLAY_LABELS),
        allowed_transitions={k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()},
    )


@router.patch("/{request_id}/lifecycle", response_model=LifecycleTransitionResponse)
async def update_recommendation_lifecycle(
    request_id: UUID,
    body: LifecycleTransitionRequest,
    x_user_name: Optional[str] = Header(default=None, alias="X-User-Name"),
):
    """Update adoption lifecycle for a stored recommendation (audit trail recorded)."""
    changed_by = (body.changed_by or x_user_name or "").strip()
    if not changed_by:
        raise HTTPException(
            status_code=400,
            detail="changed_by is required (request body or X-User-Name header)",
        )
    svc = RecommendationLifecycleService()
    try:
        result = svc.transition(
            request_id=request_id,
            to_status=body.status,
            changed_by=changed_by,
            notes=body.notes,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Recommendation not found") from None
    except InvalidLifecycleTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    status = result["lifecycle_status"]
    return LifecycleTransitionResponse(
        request_id=result["request_id"],
        lifecycle_status=status,
        lifecycle_status_label=lifecycle_display_label(status),
        lifecycle_updated_at=result["lifecycle_updated_at"],
        lifecycle_updated_by=result["lifecycle_updated_by"],
        allowed_next_statuses=result["allowed_next_statuses"],
        event=LifecycleEventResponse(**result["event"]),
    )


@router.get("/{request_id}/lifecycle/events", response_model=List[LifecycleEventResponse])
async def list_lifecycle_events(request_id: UUID):
    """List lifecycle audit events for a recommendation."""
    svc = RecommendationLifecycleService()
    rec = svc.get_history(request_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    events = svc.list_events(request_id)
    return [LifecycleEventResponse(**e) for e in events]


@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendation(
    request: GenerateRecommendationRequest,
    cost_logger=Depends(get_cost_logger),
):
    """Generate a utilization-based recommendation for a single job run."""
    validate_intent(request.intent)
    validate_recommendation_request(
        job_id=request.job_id,
        start_date=request.start_date,
        end_date=request.end_date,
        job_run_id=request.job_run_id,
    )

    request_id = uuid4()
    start_time = time.perf_counter()
    cost_logger.log_request(
        request_id=request_id,
        endpoint="/api/recommendations/generate",
        request_params=request.model_dump() if hasattr(request, "model_dump") else request.dict(),
        status="processing",
        job_id=request.job_id,
    )
    try:
        logger.info(
            "generating_recommendation",
            job_id=request.job_id,
            job_run_id=request.job_run_id,
        )

        profile_svc = AgentProfileService()
        workspace_agent_svc = WorkspaceAgentService()
        agent_id = request.agent_id
        settings_override = None
        settings_secrets = None

        if request.workspace_agent_id and request.profile_id:
            raise HTTPException(
                status_code=400,
                detail="Use either workspace_agent_id or profile_id, not both",
            )

        if request.workspace_agent_id:
            from uuid import UUID

            try:
                resolved_agent_id, settings_override, settings_secrets = (
                    workspace_agent_svc.resolve_settings_for_agent(UUID(request.workspace_agent_id))
                )
            except LookupError:
                raise HTTPException(status_code=404, detail="Workspace agent not found") from None
            if resolved_agent_id != agent_id:
                raise HTTPException(
                    status_code=400,
                    detail="workspace_agent_id does not match agent_id",
                )
        elif request.profile_id:
            from uuid import UUID

            prof = profile_svc.get_profile(UUID(request.profile_id))
            if not prof:
                raise HTTPException(status_code=404, detail="Agent profile not found")
            if prof.agent_id != agent_id:
                raise HTTPException(
                    status_code=400,
                    detail="profile_id does not match agent_id",
                )
            settings_override = prof.overrides

        effective_settings = get_agent_settings(
            agent_id,
            overrides=settings_override,
            secrets=settings_secrets,
        )
        agent = get_agent(agent_id, overrides={"settings": effective_settings})

        result = await agent.generate_recommendation(
            job_id=request.job_id,
            job_run_id=request.job_run_id,
            start_date=request.start_date,
            end_date=request.end_date,
            include_explanation=request.include_explanation,
            job_run_ingest=request.job_run_ingest,
            request_log_request_id=request_id,
        )

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="success",
            duration_ms=duration_ms,
        )

        return RecommendationResponse(
            request_id=result.get("request_id"),
            job_run_id=result.get("job_run_id"),
            current_configuration=result.get("current_configuration"),
            recommendation=result["recommendation"],
            explanation=result.get("explanation") or "",
            pattern_analysis=result.get("pattern_analysis") or "",
            risk_assessment=result.get("risk_assessment") or {},
            reason_codes=result.get("reason_codes") or [],
            job_run_ingest=result.get("job_run_ingest"),
            sizing_hints=result.get("sizing_hints"),
            llm_recommendation=result.get("llm_recommendation"),
            guardrail_recommendation=result.get("guardrail_recommendation"),
            guardrail_adjustments=result.get("guardrail_adjustments") or [],
            recommendation_attempts=result.get("recommendation_attempts", 1),
            comparison=result.get("comparison"),
            token_usage_analysis=result.get("token_usage_analysis"),
        )
    except NoJobMetricsError as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="no_metrics",
            duration_ms=duration_ms,
            error_code=e.error_code,
            error_message=e.message,
        )
        raise
    except AzureOpenAINotConfiguredError:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="error",
            duration_ms=duration_ms,
            error_code="AZURE_OPENAI_NOT_CONFIGURED",
            error_message="Azure OpenAI is not configured",
        )
        raise
    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="error",
            duration_ms=duration_ms,
            error_code="INTERNAL_ERROR",
            error_message=str(e),
        )
        logger.exception("recommendation_generation_error")
        raise HTTPException(status_code=500, detail=str(e))
