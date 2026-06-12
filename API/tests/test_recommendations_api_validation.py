"""HTTP-level validation of per-job-run recommendation API (ASGI, mock LLM)."""

import json
import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

_sample_csv = project_root / "data" / "sample_job_metrics.csv"
_sample_ingest_path = Path(
    "/Users/sabbineni/projects/generic/copilot_agent_skills/backup/sample_job_run_metrics.json"
)

os.environ.setdefault("USE_LOCAL_DATA", "true")
os.environ.setdefault("LOCAL_DATA_PATH", str(_sample_csv))
os.environ.setdefault("USE_POSTGRES", "false")
os.environ.setdefault("USE_MOCK_LLM", "true")

try:
    from API.src.deps import reset_dependencies
    from API.src.main import app
except ImportError as e:
    pytest.skip(f"Could not import app: {e}", allow_module_level=True)


@pytest.fixture
def api_client():
    reset_dependencies()
    yield
    app.dependency_overrides.clear()
    reset_dependencies()


@pytest.mark.asyncio
async def test_generate_requires_job_run_id(api_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-001",
                "start_date": "2024-01-15",
                "end_date": "2024-01-18",
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_unknown_run_returns_404(api_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-001",
                "cluster_id": "nonexistent-run",
            },
        )
    assert response.status_code == 404
    assert response.json().get("error_code") == "NO_JOB_METRICS"


@pytest.mark.asyncio
async def test_generate_success_per_run_without_dates(api_client):
    """Run-centric recommend: metrics resolved by job_run_id only."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-001",
                "cluster_id": "run-001-001",
                "include_explanation": False,
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cluster_id"] == "run-001-001"
    assert data["job_cluster_metrics"]["avg_worker_nodes_consumed"] == 4.2


@pytest.mark.asyncio
async def test_generate_success_per_run(api_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-001",
                "cluster_id": "run-001-001",
                "start_date": "2026-06-01",
                "end_date": "2026-06-03",
                "include_explanation": False,
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["cluster_id"] == "run-001-001"
    assert data["request_id"]
    assert data["recommendation"]["node_family"] in ("D", "E", "F", "L")
    assert "max_workers" in data["recommendation"]
    assert data["reason_codes"]
    assert isinstance(data["reason_codes"], list)
    assert data["job_cluster_metrics"]["azure_worker_vm_size"] == "Standard_E8s_v3"
    assert data["job_cluster_metrics"]["p99_worker_nodes_consumed"] == 8.0
    assert data["sizing_hints"]["recommended_max_workers"] >= 1
    assert data["llm_recommendation"]["node_family"] in ("D", "E", "F", "L")
    assert data["guardrail_recommendation"]["max_workers"] == data["recommendation"]["max_workers"]
    assert data["recommendation_attempts"] >= 1
    assert isinstance(data["guardrail_adjustments"], list)
    assert data["comparison"]["schema_version"] == "2.0.0"
    assert "current_configuration" in data["comparison"]["comparison"]
    comp = data["comparison"]["comparison"]
    assert "change_required" in comp
    assert comp["current_configuration"]["azure_node_type"] == "Standard_E8s_v3"
    assert data["explanation"] == ""
    assert "### 1. Workload type" in (data.get("pattern_analysis") or "")


@pytest.mark.asyncio
async def test_generate_with_prebuilt_ingest(api_client):
    if not _sample_ingest_path.is_file():
        pytest.skip("Copilot sample ingest not on this machine")
    ingest = json.loads(_sample_ingest_path.read_text())
    ingest["job_id"] = "1234567890"
    ingest["job_run_id"] = "34567894"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": ingest["job_id"],
                "job_run_id": ingest["job_run_id"],
                "start_date": "2026-04-30",
                "end_date": "2026-04-30",
                "job_run_ingest": ingest,
                "include_explanation": True,
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["job_run_ingest"]["workflow_task_count"] == 10
    assert data["job_run_ingest"]["p95_worker_nodes_consumed"] == 2
    assert len(data["explanation"]) > 0
    assert (
        "OVERPROVISIONED_AUTOSCALE" in data["reason_codes"]
        or "PER_NODE_UNDERUTILIZED" in data["reason_codes"]
    )


@pytest.mark.asyncio
async def test_generate_with_explanation(api_client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/recommendations/generate",
            json={
                "job_id": "job-001",
                "cluster_id": "run-001-002",
                "include_explanation": True,
            },
        )
    assert response.status_code == 200
    assert len(response.json().get("explanation", "")) > 0
