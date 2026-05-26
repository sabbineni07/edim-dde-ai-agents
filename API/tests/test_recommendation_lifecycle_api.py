"""API tests for recommendation lifecycle meta and validation."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("USE_POSTGRES", "false")

from API.src.main import app
from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService


@pytest.mark.asyncio
async def test_lifecycle_meta():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/recommendations/lifecycle/meta")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "RECOMMENDED" in body["statuses"]
        assert body["display_labels"]["ACCEPTED"] == "Accepted"
        assert "ACCEPTED" in body["allowed_transitions"]["RECOMMENDED"]


@pytest.mark.asyncio
async def test_lifecycle_patch_not_found(monkeypatch):
    def _missing(self, request_id, to_status, changed_by, notes=None):
        raise LookupError("Recommendation not found")

    monkeypatch.setattr(RecommendationLifecycleService, "transition", _missing)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.patch(
            "/api/recommendations/00000000-0000-0000-0000-000000000099/lifecycle",
            json={"status": "ACCEPTED", "changed_by": "tester@example.com"},
        )
        assert resp.status_code == 404, resp.text
