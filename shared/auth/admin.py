"""Admin authorization helpers."""

from __future__ import annotations

from typing import Optional, Set

from shared.config.loader import get_platform_settings


def _admin_usernames() -> Set[str]:
    raw = (get_platform_settings().admin_usernames or "admin").strip()
    return {u.strip().lower() for u in raw.split(",") if u.strip()}


def is_admin(username: Optional[str]) -> bool:
    name = (username or "").strip().lower()
    return bool(name) and name in _admin_usernames()


def list_admin_usernames() -> list[str]:
    return sorted(_admin_usernames())
