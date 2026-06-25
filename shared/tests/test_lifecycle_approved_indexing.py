"""Lifecycle transition triggers approve-only indexing."""

from unittest.mock import MagicMock, patch
from uuid import uuid4


def test_transition_to_approved_calls_indexer():
    from shared.services.recommendation_lifecycle_service import RecommendationLifecycleService

    request_id = uuid4()
    rec = MagicMock()
    rec.lifecycle_status = "MONITORING_AND_VALIDATION"
    rec.recommendation = {}
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = rec

    with patch(
        "shared.services.recommendation_lifecycle_service.DATABASE_AVAILABLE",
        True,
    ):
        with patch(
            "shared.services.recommendation_lifecycle_service.get_database_session",
            return_value=session,
        ):
            with patch("shared.rag.approved_indexing.index_approved_recommendation") as index_mock:
                svc = RecommendationLifecycleService()
                svc.transition(
                    request_id,
                    to_status="APPROVED",
                    changed_by="tester",
                )
                index_mock.assert_called_once_with(request_id)
