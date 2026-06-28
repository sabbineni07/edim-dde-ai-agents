"""Normalize Azure / Foundry endpoints to OpenAI v1 base URLs."""

from __future__ import annotations


def resolve_openai_v1_base_url(endpoint: str) -> str:
    """Return ``{resource-base}/openai/v1/`` for LangChain OpenAI v1 clients.

    Accepts classic Azure OpenAI hosts, Foundry resource hosts, and project URLs.
    """
    raw = (endpoint or "").strip().rstrip("/")
    if not raw:
        raise ValueError("Azure OpenAI / Foundry endpoint not configured")

    if "/api/projects/" in raw:
        raw = raw.split("/api/projects/")[0].rstrip("/")

    if raw.endswith("/openai/v1"):
        return f"{raw}/"
    if raw.endswith("/openai/v1/"):
        return raw

    return f"{raw}/openai/v1/"
