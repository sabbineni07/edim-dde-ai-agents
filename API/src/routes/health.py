"""Health check endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    version: str


class ReadinessResponse(BaseModel):
    """Readiness check response model."""
    status: str


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    """Readiness check endpoint (verifies app can serve requests)."""
    return ReadinessResponse(status="ready")

