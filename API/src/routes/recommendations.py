"""Recommendation endpoints."""

import time
from typing import Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from API.src.deps import get_cost_logger, get_recommendation_agent_dep
from shared.guardrails import NoJobMetricsError, validate_intent, validate_recommendation_request
from shared.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Supported intent for stay-on-topic guardrail
SUPPORTED_INTENT = "cluster_recommendation"


class GenerateRecommendationRequest(BaseModel):
    """Request model for generating recommendations."""

    job_id: str = Field(..., min_length=1, description="Databricks job ID")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    intent: Optional[str] = Field(
        default=SUPPORTED_INTENT,
        description="Request intent; only 'cluster_recommendation' is supported (stay-on-topic).",
    )


class RecommendationResponse(BaseModel):
    """Response model for recommendations."""

    request_id: Optional[str] = None
    current_configuration: Optional[Dict] = None
    recommendation: Dict
    explanation: str
    pattern_analysis: str
    risk_assessment: Dict
    token_usage_analysis: Optional[Dict] = None


@router.post("/generate", response_model=RecommendationResponse)
async def generate_recommendation(
    request: GenerateRecommendationRequest,
    agent=Depends(get_recommendation_agent_dep),
    cost_logger=Depends(get_cost_logger),
):
    """Generate a recommendation for a job.

    Args:
        request: Request containing job_id and date range
        agent: Cluster config agent (injected)

    Returns:
        Recommendation with explanation and analysis
    """
    # Input guardrails + stay-on-topic (before any LLM call)
    validate_intent(request.intent)
    validate_recommendation_request(
        job_id=request.job_id,
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
    try:
        logger.info("generating_recommendation", job_id=request.job_id)

        result = await agent.generate_recommendation(
            job_id=request.job_id,
            start_date=request.start_date,
            end_date=request.end_date,
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
            current_configuration=result.get("current_configuration"),
            recommendation=result["recommendation"],
            explanation=result["explanation"],
            pattern_analysis=result["pattern_analysis"],
            risk_assessment=result["risk_assessment"],
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
    except Exception as e:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        cost_logger.update_request(
            request_id=request_id,
            status="error",
            duration_ms=duration_ms,
            error_code="INTERNAL_ERROR",
            error_message=str(e),
        )
        logger.error("recommendation_generation_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
