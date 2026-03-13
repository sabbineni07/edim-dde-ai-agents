"""Agent discovery and listing endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from AI.src.agents.registry import get_registered_agent_ids

router = APIRouter()


class AgentsListResponse(BaseModel):
    """Response model for agents list."""

    agent_ids: list[str]


@router.get("/", response_model=AgentsListResponse)
async def list_agents():
    """List all registered agent IDs."""
    return AgentsListResponse(agent_ids=get_registered_agent_ids())
