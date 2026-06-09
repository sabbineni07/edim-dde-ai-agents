"""Shared date-range validation for browse/query APIs."""

from __future__ import annotations

import re
from datetime import datetime

from shared.config.settings import settings
from shared.guardrails.exceptions import GuardrailValidationError

DATE_FMT = "%Y-%m-%d"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_MAX_DAYS_DEFAULT = 30


def max_browse_date_range_days() -> int:
    return int(getattr(settings, "guardrail_max_date_range_days", _MAX_DAYS_DEFAULT))


def parse_date_range(start_date: str, end_date: str) -> tuple:
    """Parse and validate YYYY-MM-DD pair. Raises GuardrailValidationError on failure."""
    if not DATE_PATTERN.match(str(start_date).strip()):
        raise GuardrailValidationError(
            f"start_date must be YYYY-MM-DD, got {start_date!r}.",
            error_code="INVALID_INPUT",
        )
    if not DATE_PATTERN.match(str(end_date).strip()):
        raise GuardrailValidationError(
            f"end_date must be YYYY-MM-DD, got {end_date!r}.",
            error_code="INVALID_INPUT",
        )
    try:
        start_d = datetime.strptime(str(start_date).strip(), DATE_FMT).date()
        end_d = datetime.strptime(str(end_date).strip(), DATE_FMT).date()
    except ValueError as e:
        raise GuardrailValidationError(
            f"Invalid date format: {e}.",
            error_code="INVALID_INPUT",
        ) from e
    if end_d < start_d:
        raise GuardrailValidationError(
            "end_date must be >= start_date.",
            error_code="INVALID_INPUT",
        )
    return start_d, end_d


def validate_browse_date_range(
    start_date: str, end_date: str, *, max_days: int | None = None
) -> None:
    """Enforce max lookback for jobs/runs browse APIs."""
    start_d, end_d = parse_date_range(start_date, end_date)
    limit = max_days if max_days is not None else max_browse_date_range_days()
    if (end_d - start_d).days > limit:
        raise GuardrailValidationError(
            f"Date range must not exceed {limit} days.",
            error_code="INVALID_INPUT",
        )
