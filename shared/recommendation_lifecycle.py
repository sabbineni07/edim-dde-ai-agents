"""Recommendation adoption lifecycle (separate from API request status)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

# Primary workflow (forward)
LIFECYCLE_RECOMMENDED = "RECOMMENDED"
LIFECYCLE_ACCEPTED = "ACCEPTED"
LIFECYCLE_DEPLOYED = "DEPLOYED"
LIFECYCLE_MONITORING_AND_VALIDATION = "MONITORING_AND_VALIDATION"
LIFECYCLE_APPROVED = "APPROVED"

# Terminal / exceptional
LIFECYCLE_REJECTED = "REJECTED"
LIFECYCLE_SUPERSEDED = "SUPERSEDED"
LIFECYCLE_CANCELLED = "CANCELLED"

ALL_LIFECYCLE_STATUSES = {
    LIFECYCLE_RECOMMENDED,
    LIFECYCLE_ACCEPTED,
    LIFECYCLE_DEPLOYED,
    LIFECYCLE_MONITORING_AND_VALIDATION,
    LIFECYCLE_APPROVED,
    LIFECYCLE_REJECTED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_CANCELLED,
}

TERMINAL_LIFECYCLE_STATUSES = {
    LIFECYCLE_APPROVED,
    LIFECYCLE_REJECTED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_CANCELLED,
}

LIFECYCLE_DISPLAY_LABELS: Dict[str, str] = {
    LIFECYCLE_RECOMMENDED: "Recommended",
    LIFECYCLE_ACCEPTED: "Accepted",
    LIFECYCLE_DEPLOYED: "Deployed",
    LIFECYCLE_MONITORING_AND_VALIDATION: "Monitoring and validation",
    LIFECYCLE_APPROVED: "Approved",
    LIFECYCLE_REJECTED: "Rejected",
    LIFECYCLE_SUPERSEDED: "Superseded",
    LIFECYCLE_CANCELLED: "Cancelled",
}

ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    LIFECYCLE_RECOMMENDED: {
        LIFECYCLE_ACCEPTED,
        LIFECYCLE_REJECTED,
        LIFECYCLE_SUPERSEDED,
        LIFECYCLE_CANCELLED,
    },
    LIFECYCLE_ACCEPTED: {
        LIFECYCLE_DEPLOYED,
        LIFECYCLE_REJECTED,
        LIFECYCLE_SUPERSEDED,
        LIFECYCLE_CANCELLED,
    },
    LIFECYCLE_DEPLOYED: {
        LIFECYCLE_MONITORING_AND_VALIDATION,
        LIFECYCLE_REJECTED,
        LIFECYCLE_SUPERSEDED,
        LIFECYCLE_CANCELLED,
    },
    LIFECYCLE_MONITORING_AND_VALIDATION: {
        LIFECYCLE_APPROVED,
        LIFECYCLE_REJECTED,
        LIFECYCLE_SUPERSEDED,
        LIFECYCLE_CANCELLED,
    },
    LIFECYCLE_APPROVED: set(),
    LIFECYCLE_REJECTED: set(),
    LIFECYCLE_SUPERSEDED: set(),
    LIFECYCLE_CANCELLED: set(),
}


class InvalidLifecycleTransitionError(ValueError):
    """Raised when a lifecycle status change is not allowed."""

    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Cannot transition lifecycle from {from_status!r} to {to_status!r}. "
            f"Allowed next: {sorted(ALLOWED_TRANSITIONS.get(from_status, set()))}"
        )


def normalize_lifecycle_status(status: Optional[str]) -> str:
    if not status or not str(status).strip():
        return LIFECYCLE_RECOMMENDED
    normalized = str(status).strip().upper()
    if normalized not in ALL_LIFECYCLE_STATUSES:
        raise ValueError(f"Unknown lifecycle status: {status!r}")
    return normalized


def allowed_next_statuses(current: Optional[str]) -> List[str]:
    cur = normalize_lifecycle_status(current)
    return sorted(ALLOWED_TRANSITIONS.get(cur, set()))


def validate_transition(from_status: Optional[str], to_status: str) -> str:
    cur = normalize_lifecycle_status(from_status)
    nxt = normalize_lifecycle_status(to_status)
    if nxt not in ALLOWED_TRANSITIONS.get(cur, set()):
        raise InvalidLifecycleTransitionError(cur, nxt)
    return nxt


def lifecycle_display_label(status: Optional[str]) -> str:
    return LIFECYCLE_DISPLAY_LABELS.get(normalize_lifecycle_status(status), status or "Recommended")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def patch_stored_recommendation_lifecycle(
    recommendation: Dict[str, Any],
    *,
    status: str,
    changed_by: str,
    changed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Update nested lifecycle block in stored recommendation JSON for exports."""
    at = changed_at or utc_now()
    at_iso = at.isoformat()
    out = dict(recommendation) if recommendation else {}
    lifecycle = dict(out.get("lifecycle") or {})
    lifecycle["status"] = status
    lifecycle["updated_by"] = changed_by
    lifecycle["updated_at"] = at_iso

    if status == LIFECYCLE_ACCEPTED:
        lifecycle["accepted"] = True
        lifecycle["accepted_by"] = changed_by
        lifecycle["accepted_at"] = at_iso
    elif status == LIFECYCLE_DEPLOYED:
        lifecycle["applied"] = True
        lifecycle["applied_by"] = changed_by
        lifecycle["applied_at"] = at_iso
    elif status == LIFECYCLE_APPROVED:
        lifecycle["verified"] = True
        lifecycle["verified_by"] = changed_by
        lifecycle["verified_at"] = at_iso

    out["lifecycle"] = lifecycle
    return out
