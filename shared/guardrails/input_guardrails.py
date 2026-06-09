"""Input guardrails: validate job_id, optional date range, and intent before calling LLMs."""

from shared.config.settings import settings
from shared.guardrails.date_range import validate_browse_date_range
from shared.guardrails.exceptions import GuardrailValidationError, TopicNotSupportedError
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _max_job_id_length() -> int:
    return getattr(settings, "guardrail_max_job_id_length", 256)


def _supported_intent() -> str:
    return getattr(settings, "guardrail_supported_intent", "cluster_recommendation")


def validate_recommendation_request(
    job_id: str,
    job_run_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Validate per-run recommendation inputs. Raises GuardrailValidationError if invalid.

    Recommendations are run-centric: job_id and job_run_id are required.
    start_date/end_date are optional (metrics are resolved by job_run_id when omitted).
    When both dates are supplied, they are validated and capped by the browse guardrail.
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

    if job_run_id is None:
        raise GuardrailValidationError(
            "job_run_id is required and cannot be empty.",
            error_code="INVALID_INPUT",
        )
    run_str = str(job_run_id).strip()
    if not run_str:
        raise GuardrailValidationError(
            "job_run_id is required and cannot be empty.",
            error_code="INVALID_INPUT",
        )
    if len(run_str) > max_len:
        raise GuardrailValidationError(
            f"job_run_id length exceeds maximum ({max_len} characters).",
            error_code="INVALID_INPUT",
        )

    has_start = bool(start_date and str(start_date).strip())
    has_end = bool(end_date and str(end_date).strip())
    if has_start != has_end:
        raise GuardrailValidationError(
            "start_date and end_date must both be provided or both omitted.",
            error_code="INVALID_INPUT",
        )
    if has_start and has_end:
        validate_browse_date_range(str(start_date).strip(), str(end_date).strip())


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
