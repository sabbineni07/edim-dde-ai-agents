"""Exceptions for guardrails (input, output, safety)."""


class GuardrailValidationError(Exception):
    """Base for guardrail validation failures."""

    def __init__(self, message: str, error_code: str = "GUARDRAIL_VALIDATION"):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


class NoJobMetricsError(GuardrailValidationError):
    """Raised when no job metrics are found for the given job_id/date range.
    Used to avoid calling LLMs when there is nothing to analyze.
    """

    def __init__(self, job_id: str, start_date: str, end_date: str):
        self.job_id = job_id
        self.start_date = start_date
        self.end_date = end_date
        message = (
            f"No job metrics found for job_id={job_id!r} in date range "
            f"{start_date!r} to {end_date!r}. Cannot generate recommendation."
        )
        super().__init__(message, error_code="NO_JOB_METRICS")


class TopicNotSupportedError(GuardrailValidationError):
    """Raised when the request intent is not supported (stay-on-topic guard).
    Used to avoid unnecessary LLM token cost for off-topic requests.
    """

    def __init__(self, intent: str, supported: str = "cluster_recommendation"):
        self.intent = intent
        self.supported = supported
        message = (
            f"Topic or intent {intent!r} is not supported. "
            f"Only {supported} requests are accepted."
        )
        super().__init__(message, error_code="TOPIC_NOT_SUPPORTED")
