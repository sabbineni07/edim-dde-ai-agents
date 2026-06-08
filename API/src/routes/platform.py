"""Platform metadata for UI (guardrails, sample data hints)."""

from fastapi import APIRouter
from pydantic import BaseModel

from shared.config.connection_types import list_connection_types
from shared.config.settings import settings

router = APIRouter()


class UiHintsResponse(BaseModel):
    guardrail_max_date_range_days: int
    use_local_data: bool
    sample_data_start_date: str
    sample_data_end_date: str
    default_agent_id: str = "job_run_cluster_sizing"


@router.get("/connection-types")
async def get_connection_types():
    """Connection type catalog and form field metadata for the UI."""
    return {"connection_types": list_connection_types()}


@router.get("/ui-hints", response_model=UiHintsResponse)
async def get_ui_hints():
    """Hints for date ranges and guardrails in the Angular UI."""
    return UiHintsResponse(
        guardrail_max_date_range_days=settings.guardrail_max_date_range_days,
        use_local_data=settings.use_local_data,
        sample_data_start_date="2026-06-01",
        sample_data_end_date="2026-06-03",
    )
