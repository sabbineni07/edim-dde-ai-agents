"""Load agent prompts from Postgres (or seed fallback) for LangChain chains."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from shared.config.agent_content_seed import AGENT_PROMPTS, AUTO_TERMINATION_PLACEHOLDER
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
from shared.config.settings import Settings
from shared.services.agent_content_service import get_prompt_content, seed_agent_content_if_empty
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Resolved at chain build time (not passed to LLM invoke).
_RUNTIME_FORMAT_KEYS = frozenset({"auto_termination_minutes"})


def _seed_prompt_map() -> Dict[tuple[str, str, str], str]:
    out: Dict[tuple[str, str, str], str] = {}
    for item in AGENT_PROMPTS:
        key = (item["agent_id"], item["chain_name"], item["role"])
        out[key] = item["content"]
    return out


_SEED_BY_KEY = _seed_prompt_map()


def _fallback_prompt(agent_id: str, chain_name: str, role: str) -> Optional[str]:
    return _SEED_BY_KEY.get((agent_id, chain_name, role))


def _apply_runtime_formats(content: str, format_kwargs: Optional[Dict[str, Any]]) -> str:
    if not format_kwargs:
        return content
    text = content
    for key, value in format_kwargs.items():
        if key not in _RUNTIME_FORMAT_KEYS:
            continue
        token = "{" + key + "}"
        if token in text or key == "auto_termination_minutes":
            text = text.replace(AUTO_TERMINATION_PLACEHOLDER, str(value))
            text = text.replace(token, str(value))
    return text


def get_prompt_text(
    agent_id: str,
    chain_name: str,
    role: str,
    *,
    format_kwargs: Optional[Dict[str, Any]] = None,
) -> str:
    """Return prompt body; falls back to seed when store has no row."""
    seed_agent_content_if_empty()
    stored = get_prompt_content(agent_id, chain_name, role)
    text = stored if stored is not None else _fallback_prompt(agent_id, chain_name, role)
    if text is None:
        raise KeyError(f"No prompt for {agent_id}/{chain_name}/{role}")
    return _apply_runtime_formats(text, format_kwargs)


def get_guardrail_retry_instruction(agent_id: str = DBX_CLUSTER_TUNING_AGENT_ID) -> str:
    return get_prompt_text(agent_id, "guardrail_retry", "system")


def build_chain_messages(
    agent_id: str,
    chain_name: str,
    *,
    settings: Optional[Settings] = None,
) -> List[Tuple[str, str]]:
    """Build (role, content) pairs for ChatPromptTemplate.from_messages."""
    format_kwargs: Dict[str, Any] = {}
    if chain_name == "sizing" and settings is not None:
        format_kwargs["auto_termination_minutes"] = int(
            settings.recommendation_auto_termination_minutes or 0
        )
    if chain_name == "guardrail_retry":
        return [
            ("system", get_prompt_text(agent_id, chain_name, "system", format_kwargs=format_kwargs))
        ]
    messages: List[Tuple[str, str]] = []
    for role in ("system", "human"):
        try:
            messages.append(
                (
                    role,
                    get_prompt_text(
                        agent_id,
                        chain_name,
                        role,
                        format_kwargs=format_kwargs,
                    ),
                )
            )
        except KeyError:
            logger.warning("prompt_message_missing", agent_id=agent_id, chain=chain_name, role=role)
    return messages
