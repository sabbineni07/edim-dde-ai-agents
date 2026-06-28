"""Recommendation endpoints."""

import time
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from AI.src.core.llm.foundry_llm_service import FoundryLLMNotConfiguredError
from API.src.deps import get_agent, get_cost_logger
from DE.src.access.recommendation_metrics import fetch_job_run_metrics_for_recommendation
from shared.config.loader import get_agent_settings
from shared.factories.data_collector_context import reset_metrics_collector, set_metrics_collector
from shared.guardrails import NoJobMetricsError, validate_intent, validate_recommendation_request
from shared.recommendation_lifecycle import (
    ALLOWED_TRANSITIONS,
    LIFECYCLE_DISPLAY_LABELS,
    InvalidLifecycleTransitionError,
    allowed_next_statuses,
    lifecycle_display_label,
    normalize_lifecycle_status,
)
from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService
from shared.services.workspace_agent_service import WorkspaceAgentService
from shared.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

SUPPORTED_INTENT = "cluster_recommendation"


class GenerateRecommendationRequest(BaseModel):
    """Request model for per-job-run cluster recommendations."""

    agent_id: str = Field(
        default="dbx_cluster_tuning_agent",
        description="Which agent to run (default: dbx_cluster_tuning_agent).",
    )
    workspace_agent_id: Optional[str] = Field(
        default=None,
        description="Workspace agent install id (UUID); resolves connection bindings.",
    )
    job_id: str = Field(..., min_length=1, description="Databricks job ID")
    cluster_id: str = Field(
        ...,
        min_length=1,
        description="Cluster identifier for the job run's attached cluster.",
    )
    job_run_id: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Workflow job run identifier (optional; resolved from metrics when omitted).",
    )
    environment_id: Optional[str] = Field(
        default=None,
        description="Metrics environment id (same as job browse APIs).",
    )
    connection_id: Optional[str] = Field(
        default=None,
        description="Optional metrics connection override (UUID).",
    )
    dataset_id: Optional[str] = Field(
        default=None,
        description="Optional metrics dataset override (UUID).",
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Optional browse window start (YYYY-MM-DD). Omitted = resolve metrics by cluster_id/job_run_id only.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Optional browse window end (YYYY-MM-DD). Must be provided with start_date when set.",
    )
    include_explanation: bool = Field(
        default=False,
        description="If true, run explanation LLM chain (slower). Default false for UI on-demand.",
    )
    job_cluster_metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional precomputed job-run ingest. Skips collector when set.",
    )
    job_run_ingest: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Deprecated alias for job_cluster_metrics.",
    )

    @model_validator(mode="after")
    def _normalize_metrics_alias(self) -> "GenerateRecommendationRequest":
        metrics = self.job_cluster_metrics or self.job_run_ingest
        if metrics is not None:
            object.__setattr__(self, "job_cluster_metrics", metrics)
        return self

    intent: Optional[str] = Field(
        default=SUPPORTED_INTENT,
        description="Request intent; only 'cluster_recommendation' is supported.",
    )


class RecommendationResponse(BaseModel):
    """Response model for recommendations."""

    request_id: Optional[str] = None
    cluster_id: Optional[str] = None
    job_run_id: Optional[str] = None
    current_configuration: Optional[Dict] = None
    recommendation: Dict
    explanation: str = ""
    pattern_analysis: str = ""
    risk_assessment: Dict = Field(default_factory=dict)
    reason_codes: list = Field(default_factory=list)
    job_cluster_metrics: Optional[Dict] = None
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
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    """Generate a utilization-based recommendation for a single job run."""
    validate_intent(request.intent)
    validate_recommendation_request(
        job_id=request.job_id,
        cluster_id=request.cluster_id,
        job_run_id=request.job_run_id,
        start_date=request.start_date,
        end_date=request.end_date,
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
    collector_token = None
    try:
        logger.info(
            "generating_recommendation",
            job_id=request.job_id,
            cluster_id=request.cluster_id,
            job_run_id=request.job_run_id,
            environment_id=request.environment_id,
        )

        workspace_agent_svc = WorkspaceAgentService()
        agent_id = request.agent_id
        settings_override = None
        settings_secrets = None
        effective_dataset_id = request.dataset_id

        if request.workspace_agent_id:
            from uuid import UUID as _UUID

            try:
                wa_uuid = _UUID(request.workspace_agent_id)
                resolved_agent_id, settings_override, settings_secrets = (
                    workspace_agent_svc.resolve_settings_for_agent(wa_uuid)
                )
            except LookupError:
                raise HTTPException(status_code=404, detail="Workspace agent not found") from None
            if resolved_agent_id != agent_id:
                raise HTTPException(
                    status_code=400,
                    detail="workspace_agent_id does not match agent_id",
                )
            if not effective_dataset_id:
                effective_dataset_id = workspace_agent_svc.get_metrics_dataset_id(wa_uuid)
        else:
            # Option 2: no workspace agent install => RAG/search off unless explicitly bound.
            settings_override = {"vector_retrieval_backend": "none"}

        metrics_override = request.job_cluster_metrics
        if request.environment_id:
            from DE.src.access.environment_job_metrics_collector import (
                get_collector as get_job_metrics_collector,
            )

            collector = get_job_metrics_collector(
                request.environment_id,
                (x_user_id or x_user_name or "anonymous").strip() or "anonymous",
                connection_id=request.connection_id,
                dataset_id=effective_dataset_id,
            )
            collector_token = set_metrics_collector(collector)

        if not metrics_override:
            metrics_override = fetch_job_run_metrics_for_recommendation(
                environment_id=request.environment_id,
                user_id=x_user_id or x_user_name,
                connection_id=request.connection_id,
                dataset_id=effective_dataset_id,
                job_id=request.job_id,
                cluster_id=request.cluster_id,
                job_run_id=request.job_run_id,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            if not metrics_override:
                raise NoJobMetricsError(
                    job_id=request.job_id,
                    start_date=request.start_date or "",
                    end_date=request.end_date or "",
                    cluster_id=request.cluster_id,
                    job_run_id=request.job_run_id,
                )

        effective_settings = get_agent_settings(
            agent_id,
            overrides=settings_override,
            secrets=settings_secrets,
        )
        from AI.src.agents.dbx_cluster_tuning_agent.deps import build_agent_runtime_deps

        agent = get_agent(
            agent_id,
            overrides={
                "settings": effective_settings,
                **build_agent_runtime_deps(effective_settings, agent_id),
            },
        )

        result = await agent.generate_recommendation(
            job_id=request.job_id,
            cluster_id=request.cluster_id,
            job_run_id=request.job_run_id,
            start_date=request.start_date or None,
            end_date=request.end_date or None,
            include_explanation=request.include_explanation,
            job_cluster_metrics=metrics_override,
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
            cluster_id=result.get("cluster_id"),
            job_run_id=result.get("job_run_id"),
            current_configuration=result.get("current_configuration"),
            recommendation=result["recommendation"],
            explanation=result.get("explanation") or "",
            pattern_analysis=result.get("pattern_analysis") or "",
            risk_assessment=result.get("risk_assessment") or {},
            reason_codes=result.get("reason_codes") or [],
            job_cluster_metrics=result.get("job_cluster_metrics"),
            job_run_ingest=result.get("job_cluster_metrics"),
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
    except FoundryLLMNotConfiguredError:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="error",
            duration_ms=duration_ms,
            error_code="FOUNDRY_LLM_NOT_CONFIGURED",
            error_message="Azure AI Foundry LLM is not configured",
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
    finally:
        if collector_token is not None:
            reset_metrics_collector(collector_token)
