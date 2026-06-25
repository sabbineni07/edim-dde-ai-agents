"""Load platform + per-agent YAML settings and merge with env."""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Dict, Optional

from shared.config.profile_overrides import flatten_overrides, validate_profile_overrides
from shared.config.settings import Settings
from shared.config.yaml_loader import (
    config_dir,
    flatten_agent_yaml,
    flatten_platform_yaml,
    load_yaml_file,
    resolve_value,
)

_platform_cache: Optional[Settings] = None
_agent_cache: Dict[str, Settings] = {}


def _env_file_usable() -> bool:
    if not os.path.exists(".env"):
        return False
    try:
        with open(".env", "r"):
            return True
    except (PermissionError, OSError):
        return False


def _build_settings(flat: Dict) -> Settings:
    """Build Settings: YAML init values, then environment overrides secrets."""
    resolved = resolve_value(flat)
    clean = {k: v for k, v in resolved.items() if v is not None}
    try:
        if _env_file_usable():
            return Settings(**clean)
        return Settings(_env_file=None, **clean)
    except Exception as e:
        warnings.warn(f"Error loading settings: {e}. Using defaults.")
        return Settings(_env_file=None, **clean)


def load_platform_dict() -> Dict:
    path = config_dir() / "platform.yaml"
    raw = load_yaml_file(path)
    return flatten_platform_yaml(raw)


def load_agent_dict(agent_id: str) -> Dict:
    path = config_dir() / "agents" / f"{agent_id}.yaml"
    raw = load_yaml_file(path)
    return flatten_agent_yaml(raw)


def get_platform_settings() -> Settings:
    """Shared platform settings (Databricks, Azure, Postgres, API)."""
    global _platform_cache
    if _platform_cache is None:
        _platform_cache = _build_settings(load_platform_dict())
    return _platform_cache


def get_agent_settings(
    agent_id: str,
    overrides: Optional[Dict] = None,
    secrets: Optional[Dict] = None,
) -> Settings:
    """Merged platform + agent YAML; agent keys override. Env overrides secrets.

    If overrides are provided (e.g., from an Agent Profile or workspace agent bindings),
    they are validated and applied on top of YAML before env is applied.

    secrets: connection-resolved tokens/keys; omitted keys leave Managed Identity path.
    """
    if overrides is not None or secrets:
        flat_overrides = validate_profile_overrides(overrides or {}) if overrides else {}
        merged = {**load_platform_dict(), **load_agent_dict(agent_id), **flat_overrides}
        if secrets:
            merged = {**merged, **{k: v for k, v in secrets.items() if v is not None}}
        return _build_settings(merged)

    if agent_id not in _agent_cache:
        merged = {**load_platform_dict(), **load_agent_dict(agent_id)}
        _agent_cache[agent_id] = _build_settings(merged)
    return _agent_cache[agent_id]


def reset_settings_cache() -> None:
    """Clear cached settings (tests)."""
    global _platform_cache
    _platform_cache = None
    _agent_cache.clear()


def agent_config_path(agent_id: str) -> Path:
    return config_dir() / "agents" / f"{agent_id}.yaml"
