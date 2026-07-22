"""Load agent prompts from Postgres (or seed fallback) for LangChain chains."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from shared.config.agent_content_seed import (
    AGENT_PROMPTS,
    AGENT_SKILLS,
    AUTO_TERMINATION_PLACEHOLDER,
)
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID, SPARK_JOB_RCA_AGENT_ID
from shared.config.settings import Settings
from shared.services.agent_content_service import (
    get_active_skill_contents,
    get_prompt_content,
    seed_agent_content_if_empty,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Resolved at chain build time (not passed to LLM invoke).
_RUNTIME_FORMAT_KEYS = frozenset({"auto_termination_minutes"})

# Chains that append active skills to the system message at runtime.
_CHAINS_WITH_SKILLS = frozenset({(SPARK_JOB_RCA_AGENT_ID, "rca")})

# Placeholders ChatPromptTemplate may substitute at invoke time (human prompts).
_CHAIN_INVOKE_PLACEHOLDERS: Dict[tuple[str, str], FrozenSet[str]] = {
    (DBX_CLUSTER_TUNING_AGENT_ID, "sizing"): frozenset(
        {
            "current_config",
            "job_run_ingest",
            "sizing_hints",
            "guardrail_feedback",
            "historical_context",
        }
    ),
    (DBX_CLUSTER_TUNING_AGENT_ID, "explanation"): frozenset(
        {
            "recommendation",
            "job_run_ingest",
            "pattern_analysis",
            "risk_assessment",
        }
    ),
    (SPARK_JOB_RCA_AGENT_ID, "rca"): frozenset(
        {
            "workspace_id",
            "job_id",
            "job_run_id",
            "job_run_date",
            "task_key",
            "classification_hint",
            "cluster_logs_section",
            "spark_metrics_section",
            "query_plans_section",
            "evidence_pack",
        }
    ),
}


def _escape_non_placeholder_braces(text: str, keep: FrozenSet[str]) -> str:
    """Double literal `{`/`}` so LangChain f-string templates ignore JSON examples.

    Keeps `{name}` intact when `name` is in `keep` (invoke-time variables).
    """
    if not text:
        return text
    protected: Dict[str, str] = {}
    out = text
    for i, key in enumerate(sorted(keep)):
        token = "{" + key + "}"
        if token not in out:
            continue
        marker = f"\x00KEEP{i}\x00"
        protected[marker] = token
        out = out.replace(token, marker)
    out = out.replace("{", "{{").replace("}", "}}")
    for marker, token in protected.items():
        out = out.replace(marker, token)
    return out


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


def _seed_skills_block(agent_id: str) -> str:
    parts: List[str] = []
    for item in sorted(
        (s for s in AGENT_SKILLS if s["agent_id"] == agent_id),
        key=lambda s: (int(s.get("sort_order") or 0), s.get("skill_key") or ""),
    ):
        title = item.get("title") or item.get("skill_key") or "Skill"
        content = (item.get("content") or "").strip()
        if content:
            parts.append(f"### {title}\n{content}")
    return "\n\n".join(parts)


def _skills_block_for_agent(agent_id: str) -> str:
    """Active skills from store, falling back to seed content."""
    seed_agent_content_if_empty()
    stored = get_active_skill_contents(agent_id)
    if stored:
        parts = []
        for item in stored:
            title = item.get("title") or item.get("skill_key") or "Skill"
            content = (item.get("content") or "").strip()
            if content:
                parts.append(f"### {title}\n{content}")
        return "\n\n".join(parts)
    return _seed_skills_block(agent_id)


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
    invoke_vars = _CHAIN_INVOKE_PLACEHOLDERS.get((agent_id, chain_name), frozenset())
    messages: List[Tuple[str, str]] = []
    for role in ("system", "human"):
        try:
            content = get_prompt_text(
                agent_id,
                chain_name,
                role,
                format_kwargs=format_kwargs,
            )
            if role == "system" and (agent_id, chain_name) in _CHAINS_WITH_SKILLS:
                skills = _skills_block_for_agent(agent_id)
                if skills:
                    content = f"{content}\n\n## Domain skills\n\n{skills}"
            # System prompts are literal (runtime tokens already substituted).
            # Human prompts keep only declared invoke placeholders; escape JSON `{}` examples.
            keep = invoke_vars if role == "human" else frozenset()
            content = _escape_non_placeholder_braces(content, keep)
            messages.append((role, content))
        except KeyError:
            logger.warning("prompt_message_missing", agent_id=agent_id, chain=chain_name, role=role)
    return messages
