"""Tests for Foundry / Azure OpenAI v1 endpoint resolution."""

import pytest

from shared.azure.endpoint_resolver import resolve_openai_v1_base_url


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        (
            "https://myres.openai.azure.com",
            "https://myres.openai.azure.com/openai/v1/",
        ),
        (
            "https://myres.openai.azure.com/",
            "https://myres.openai.azure.com/openai/v1/",
        ),
        (
            "https://myres.services.ai.azure.com",
            "https://myres.services.ai.azure.com/openai/v1/",
        ),
        (
            "https://myres.services.ai.azure.com/api/projects/proj-1",
            "https://myres.services.ai.azure.com/openai/v1/",
        ),
        (
            "https://myres.openai.azure.com/openai/v1",
            "https://myres.openai.azure.com/openai/v1/",
        ),
        (
            "https://myres.openai.azure.com/openai/v1/",
            "https://myres.openai.azure.com/openai/v1/",
        ),
    ],
)
def test_resolve_openai_v1_base_url(endpoint: str, expected: str) -> None:
    assert resolve_openai_v1_base_url(endpoint) == expected


def test_resolve_openai_v1_base_url_empty_raises() -> None:
    with pytest.raises(ValueError, match="not configured"):
        resolve_openai_v1_base_url("")
