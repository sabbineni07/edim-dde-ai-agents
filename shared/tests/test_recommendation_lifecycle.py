"""Unit tests for recommendation lifecycle transitions."""

import pytest

from shared.recommendation_lifecycle import (
    LIFECYCLE_ACCEPTED,
    LIFECYCLE_APPROVED,
    LIFECYCLE_DEPLOYED,
    LIFECYCLE_RECOMMENDED,
    InvalidLifecycleTransitionError,
    allowed_next_statuses,
    validate_transition,
)


def test_recommended_can_accept():
    assert validate_transition(LIFECYCLE_RECOMMENDED, LIFECYCLE_ACCEPTED) == LIFECYCLE_ACCEPTED


def test_cannot_skip_to_approved():
    with pytest.raises(InvalidLifecycleTransitionError):
        validate_transition(LIFECYCLE_RECOMMENDED, LIFECYCLE_APPROVED)


def test_full_happy_path():
    cur = LIFECYCLE_RECOMMENDED
    for nxt in (
        LIFECYCLE_ACCEPTED,
        LIFECYCLE_DEPLOYED,
        "MONITORING_AND_VALIDATION",
        LIFECYCLE_APPROVED,
    ):
        cur = validate_transition(cur, nxt)
    assert cur == LIFECYCLE_APPROVED
    assert allowed_next_statuses(cur) == []


def test_approved_is_terminal():
    assert allowed_next_statuses(LIFECYCLE_APPROVED) == []
