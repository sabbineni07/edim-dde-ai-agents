"""Spark job failure RCA endpoints."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from AI.src.core.llm.foundry_llm_service import FoundryLLMNotConfiguredError
from API.src.deps import get_agent, get_cost_logger
from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.config.loader import get_agent_settings
from shared.factories.spark_telemetry_factory import get_spark_telemetry_collector
from shared.services.rca_analysis_service import RcaAnalysisService
from shared.services.workspace_agent_service import WorkspaceAgentService
from shared.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class AnalyzeRcaRequest(BaseModel):
    job_run_id: str = Field(..., min_length=1)
    workspace_agent_id: Optional[str] = Field(
        default=None,
        description="Workspace agent install id (UUID); resolves dataset + LLM bindings.",
    )
    agent_id: str = Field(default=SPARK_JOB_RCA_AGENT_ID)
    job_id: Optional[str] = None
    job_run_date: Optional[str] = Field(
        default=None, description="Partition date YYYY-MM-DD for Delta pruning."
    )
    task_key: Optional[str] = None
    workspace_id: Optional[str] = None
    trigger_source: Optional[str] = Field(default="ui", description="pipeline | ui")
    force: bool = Field(
        default=False,
        description="If true, re-run even when an analysis already exists for this run/task.",
    )
    evidence_pack: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional precomputed evidence pack (skips collector).",
    )


class RcaResponse(BaseModel):
    request_id: str
    job_id: Optional[str] = None
    job_run_id: str
    task_key: Optional[str] = None
    status: str = "completed"
    root_cause: Dict[str, Any] = Field(default_factory=dict)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    contributing_factors: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    raw_anchors: Dict[str, Any] = Field(default_factory=dict)
    token_usage_analysis: Optional[Dict[str, Any]] = None
    cached: bool = False

    model_config = {"extra": "ignore"}


@router.post("/analyze", response_model=RcaResponse)
async def analyze_rca(
    request: AnalyzeRcaRequest,
    cost_logger=Depends(get_cost_logger),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
):
    """Run Spark failure RCA for a job_run_id (pipeline final task or UI)."""
    if request.agent_id != SPARK_JOB_RCA_AGENT_ID:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported agent_id for RCA (expected {SPARK_JOB_RCA_AGENT_ID})",
        )

    svc = RcaAnalysisService()
    if not request.force:
        existing = svc.get_by_run(request.job_run_id, request.task_key)
        if existing:
            result = dict(existing.result or {})
            result["cached"] = True
            return RcaResponse(**{**result, "cached": True})

    request_id = uuid4()
    start_time = time.perf_counter()
    try:
        cost_logger.log_request(
            request_id=request_id,
            endpoint="/api/rca/analyze",
            request_params=request.model_dump(),
            status="processing",
            job_id=request.job_id,
        )
    except Exception:
        pass

    workspace_agent_svc = WorkspaceAgentService()
    settings_override = None
    settings_secrets = None
    agent_id = request.agent_id

    if request.workspace_agent_id:
        try:
            wa_uuid = UUID(request.workspace_agent_id)
            resolved_agent_id, settings_override, settings_secrets = (
                workspace_agent_svc.resolve_settings_for_agent(wa_uuid)
            )
        except LookupError:
            raise HTTPException(status_code=404, detail="Workspace agent not found") from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if resolved_agent_id != agent_id:
            raise HTTPException(
                status_code=400,
                detail="workspace_agent_id does not match agent_id",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="workspace_agent_id is required to resolve spark_logs/spark_metrics + LLM bindings",
        )

    effective_settings = get_agent_settings(
        agent_id,
        overrides=settings_override,
        secrets=settings_secrets,
    )
    from AI.src.agents.spark_job_rca_agent.deps import build_agent_runtime_deps

    try:
        agent = get_agent(
            agent_id,
            overrides={
                "settings": effective_settings,
                "telemetry_collector": get_spark_telemetry_collector(effective_settings),
                **build_agent_runtime_deps(effective_settings, agent_id),
            },
        )
        result = agent.analyze(
            job_run_id=request.job_run_id,
            job_id=request.job_id,
            job_run_date=request.job_run_date,
            task_key=request.task_key,
            workspace_id=request.workspace_id,
            request_id=request_id,
            evidence_pack_override=request.evidence_pack,
        )
    except FoundryLLMNotConfiguredError:
        raise
    except Exception as e:
        logger.error("rca_analyze_failed", error=str(e), job_run_id=request.job_run_id)
        try:
            cost_logger.update_request(
                request_id=request_id,
                status="error",
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                error_message=str(e),
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"RCA analysis failed: {e}") from e

    # Ensure workspace_id is on result for persistence
    if request.workspace_id and not result.get("workspace_id"):
        result = {**result, "workspace_id": request.workspace_id}

    stored = svc.save(
        result=result,
        trigger_source=request.trigger_source or "ui",
        agent_id=agent_id,
        workspace_agent_id=request.workspace_agent_id,
        force=request.force,
        request_log_request_id=request_id,
    )
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    try:
        cost_logger.update_request(
            request_id=request_id,
            status="success",
            duration_ms=duration_ms,
        )
    except Exception:
        pass

    out = dict(stored.result or result)
    out["cached"] = False
    out["request_id"] = str(stored.request_id)
    logger.info(
        "rca_analyze_ok",
        request_id=str(stored.request_id),
        job_run_id=request.job_run_id,
        trigger_source=request.trigger_source,
        user=x_user_name or x_user_id,
        duration_ms=duration_ms,
    )
    return RcaResponse(**out)


@router.get("/{request_id}", response_model=RcaResponse)
async def get_rca(request_id: UUID):
    """Fetch a stored RCA by request_id."""
    svc = RcaAnalysisService()
    rec = svc.get_by_request_id(request_id)
    if not rec:
        raise HTTPException(status_code=404, detail="RCA analysis not found")
    out = dict(rec.result or {})
    out["cached"] = True
    out["request_id"] = str(rec.request_id)
    return RcaResponse(**out)
