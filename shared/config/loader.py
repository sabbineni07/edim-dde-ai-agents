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


def _settings_field_names() -> set[str]:
    return set(Settings.model_fields.keys())


def _filter_settings_kwargs(flat: Dict) -> Dict:
    """Keep only declared Settings fields; drop legacy/unknown keys (e.g. api_version)."""
    allowed = _settings_field_names()
    return {k: v for k, v in flat.items() if k in allowed and v is not None}


def _env_has_override(field_name: str) -> bool:
    field = Settings.model_fields[field_name]
    candidate_keys = {field_name, field_name.upper()}
    validation_alias = getattr(field, "validation_alias", None)
    if isinstance(validation_alias, str):
        candidate_keys.add(validation_alias)
    elif validation_alias is not None and hasattr(validation_alias, "choices"):
        candidate_keys.update(str(choice) for choice in validation_alias.choices)
    return any(os.environ.get(key) not in (None, "") for key in candidate_keys)


def _build_settings(flat: Dict, *, from_env: bool = True) -> Settings:
    """Build Settings from a flat dict.

    When ``from_env`` is False (workspace agent / profile overrides), values come only
    from the merged dict so empty platform env vars cannot wipe connection config.
    """
    resolved = resolve_value(flat)
    clean = _filter_settings_kwargs(resolved)
    if from_env:
        try:
            env_wins = {k: v for k, v in clean.items() if not _env_has_override(k)}
            if _env_file_usable():
                return Settings(**env_wins)
            return Settings(_env_file=None, **env_wins)
        except Exception as e:
            warnings.warn(f"Error loading settings: {e}. Using merged values only.")
    return Settings.model_validate(clean)


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
        _platform_cache = _build_settings(load_platform_dict(), from_env=True)
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
        return _build_settings(merged, from_env=False)

    if agent_id not in _agent_cache:
        merged = {**load_platform_dict(), **load_agent_dict(agent_id)}
        _agent_cache[agent_id] = _build_settings(merged, from_env=True)
    return _agent_cache[agent_id]


def reset_settings_cache() -> None:
    """Clear cached settings (tests)."""
    global _platform_cache
    _platform_cache = None
    _agent_cache.clear()


def agent_config_path(agent_id: str) -> Path:
    return config_dir() / "agents" / f"{agent_id}.yaml"
