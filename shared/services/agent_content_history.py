"""Version history helpers for agent prompts and skills."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from shared.config.agent_content_seed import AGENT_PROMPTS, AGENT_SKILLS
from shared.utils.text_diff import unified_diff_text


def seed_prompt_item(agent_id: str, chain_name: str, role: str) -> Optional[Dict[str, Any]]:
    for item in AGENT_PROMPTS:
        if (
            item["agent_id"] == agent_id
            and item["chain_name"] == chain_name
            and item["role"] == role
        ):
            return dict(item)
    return None


def seed_skill_item(agent_id: str, skill_key: str) -> Optional[Dict[str, Any]]:
    for item in AGENT_SKILLS:
        if item["agent_id"] == agent_id and item["skill_key"] == skill_key:
            return dict(item)
    return None


def version_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    content = str(row.get("content") or "")
    return {
        "version": int(row.get("version") or 1),
        "is_active": bool(row.get("is_active", True)),
        "updated_at": row.get("updated_at"),
        "updated_by": row.get("updated_by"),
        "content_length": len(content),
    }


def list_versions(rows: List[Dict[str, Any]], *, key_fn) -> List[Dict[str, Any]]:
    versions = sorted(rows, key=lambda r: int(r.get("version") or 1), reverse=True)
    return [version_summary(v) for v in versions]


def find_version_row(
    rows: List[Dict[str, Any]],
    *,
    version: int,
    match_fn,
) -> Optional[Dict[str, Any]]:
    for row in rows:
        if match_fn(row) and int(row.get("version") or 0) == version:
            return row
    return None


def build_content_diff(
    *,
    from_version: int,
    to_version: int,
    from_content: str,
    to_content: str,
    label_prefix: str,
) -> Dict[str, Any]:
    diff = unified_diff_text(
        from_content,
        to_content,
        from_label=f"{label_prefix} v{from_version}",
        to_label=f"{label_prefix} v{to_version}",
    )
    return {
        "from_version": from_version,
        "to_version": to_version,
        "diff": diff or "(no differences)",
        "has_changes": bool(diff),
    }


def seed_keys_for_agent(agent_id: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    prompt_keys = [
        (item["chain_name"], item["role"]) for item in AGENT_PROMPTS if item["agent_id"] == agent_id
    ]
    skill_keys = [item["skill_key"] for item in AGENT_SKILLS if item["agent_id"] == agent_id]
    return prompt_keys, skill_keys
