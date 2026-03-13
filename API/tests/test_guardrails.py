"""Tests for input/output and safety guardrails."""

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

try:
    from API.src.main import app
except ImportError as e:
    pytest.skip(f"Could not import app: {e}", allow_module_level=True)


@pytest.mark.asyncio
async def test_input_guardrail_empty_job_id_rejected():
    """Empty job_id should be rejected (422 from Pydantic or 400 from guardrail)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
    assert response.status_code in (400, 422)
    data = response.json()
    assert "detail" in data
    if response.status_code == 400:
        assert data.get("error_code") == "INVALID_INPUT"
    else:
        # Pydantic validation error
        assert any(
            "job_id" in str(d).lower()
            for d in (data["detail"] if isinstance(data["detail"], list) else [data["detail"]])
        )


@pytest.mark.asyncio
async def test_input_guardrail_invalid_date_range_returns_400():
    """end_date < start_date should return 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-1",
                "start_date": "2024-02-01",
                "end_date": "2024-01-01",
            },
        )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "end_date" in data["detail"] or "start_date" in data["detail"]


@pytest.mark.asyncio
async def test_stay_on_topic_unsupported_intent_returns_400():
    """Unsupported intent should return 400 and avoid LLM cost."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-1",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "intent": "weather_forecast",
            },
        )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert data.get("error_code") == "TOPIC_NOT_SUPPORTED"
    assert "weather_forecast" in data["detail"] or "not supported" in data["detail"].lower()


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="Runs full agent; may segfault in some envs (langchain/numpy). Run manually with real data."
)
async def test_valid_request_passes_guardrails():
    """Valid request passes input and topic guardrails; may 404 (no metrics) or 200/500."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-1",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
    # 400 = guardrail (e.g. topic); 404 = no job metrics; 500 = service error; 200 = success
    assert response.status_code in (
        200,
        404,
        500,
    ), f"Expected 200/404/500, got {response.status_code}: {response.json()}"
    if response.status_code == 404:
        data = response.json()
        assert data.get("error_code") == "NO_JOB_METRICS"
