"""Whitelisted value resolvers for YAML `${resolve:name}` placeholders."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ResolverFn = Callable[[], Any]

_REGISTRY: Dict[str, ResolverFn] = {}


def register_resolver(name: str, fn: ResolverFn) -> None:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"Invalid resolver name: {name!r}")
    _REGISTRY[name] = fn


def get_resolver(name: str) -> Optional[ResolverFn]:
    return _REGISTRY.get(name)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_openai_deployment() -> str:
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME") or "gpt-4o"


def _default_local_data_csv() -> str:
    env_path = os.environ.get("LOCAL_DATA_PATH")
    if env_path:
        return env_path
    return str(_project_root() / "data" / "sample_job_metrics.csv")


def _config_dir() -> str:
    return os.environ.get("CONFIG_DIR") or str(_project_root() / "config")


register_resolver("default_openai_deployment", _default_openai_deployment)
register_resolver("default_local_data_csv", _default_local_data_csv)
register_resolver("config_dir", _config_dir)
