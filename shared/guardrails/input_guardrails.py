"""Input guardrails: validate job_id, date range, and intent before calling LLMs."""

import re
from datetime import datetime

from shared.config.settings import settings
from shared.guardrails.exceptions import GuardrailValidationError, TopicNotSupportedError
from shared.utils.logging import get_logger

logger = get_logger(__name__)


# Configurable limits (from settings or defaults)
def _max_job_id_length() -> int:
    return getattr(settings, "guardrail_max_job_id_length", 256)


def _max_date_range_days() -> int:
    return getattr(settings, "guardrail_max_date_range_days", 365)


def _supported_intent() -> str:
    return getattr(settings, "guardrail_supported_intent", "cluster_recommendation")


# Date format expected for start_date / end_date
DATE_FMT = "%Y-%m-%d"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_recommendation_request(
    job_id: str,
    start_date: str,
    end_date: str,
) -> None:
    """Validate recommendation request inputs. Raises GuardrailValidationError if invalid.

    - job_id: non-empty, within max length
    - start_date, end_date: YYYY-MM-DD format, end >= start, range <= max_date_range_days
    """
    if not job_id or not str(job_id).strip():
        raise GuardrailValidationError(
            "job_id is required and cannot be empty.",
            error_code="INVALID_INPUT",
        )
    job_id_str = str(job_id).strip()
    max_len = _max_job_id_length()
    if len(job_id_str) > max_len:
        raise GuardrailValidationError(
            f"job_id length exceeds maximum ({max_len} characters).",
            error_code="INVALID_INPUT",
        )

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

    max_days = _max_date_range_days()
    if (end_d - start_d).days > max_days:
        raise GuardrailValidationError(
            f"Date range must not exceed {max_days} days.",
            error_code="INVALID_INPUT",
        )


def validate_intent(intent: str | None) -> None:
    """Validate that the request intent is supported (stay-on-topic).
    Raises TopicNotSupportedError if intent is provided and not supported.
    """
    if intent is None or (isinstance(intent, str) and not intent.strip()):
        return
    supported = _supported_intent()
    if str(intent).strip().lower() != supported.lower():
        logger.info("topic_not_supported", intent=intent, supported=supported)
        raise TopicNotSupportedError(intent=intent, supported=supported)
