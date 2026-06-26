"""Load and resolve YAML configuration values."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml

from shared.config.resolvers import get_resolver

_ENV_PATTERN = re.compile(r"^\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}$")
_RESOLVE_PATTERN = re.compile(r"^\$\{resolve:([A-Za-z_][A-Za-z0-9_]*)\}$")


def config_dir() -> Path:
    from shared.config.resolvers import get_resolver

    fn = get_resolver("config_dir")
    return Path(fn() if fn else os.environ.get("CONFIG_DIR", "config"))


def load_yaml_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def resolve_value(value: Any) -> Any:
    """Resolve `${env:VAR}` and `${resolve:name}` strings; recurse into collections."""
    if isinstance(value, str):
        env_m = _ENV_PATTERN.match(value.strip())
        if env_m:
            return os.environ.get(env_m.group(1))
        res_m = _RESOLVE_PATTERN.match(value.strip())
        if res_m:
            fn = get_resolver(res_m.group(1))
            if fn is None:
                raise KeyError(f"Unknown settings resolver: {res_m.group(1)}")
            return fn()
        return value
    if isinstance(value, dict):
        return {k: resolve_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_value(v) for v in value]
    return value


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge override into base (override wins)."""
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def flatten_platform_yaml(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map nested platform YAML to flat Settings field names."""
    flat: Dict[str, Any] = {}
    platform = data.get("platform") or {}
    if isinstance(platform, dict):
        for k in ("app_env", "log_level", "api_host", "api_port", "use_postgres", "use_local_data"):
            if k in platform:
                flat[k] = platform[k]
        if "local_data_path" in platform:
            flat["local_data_path"] = platform["local_data_path"]

    db = data.get("databricks") or {}
    if isinstance(db, dict):
        mapping = {
            "server_hostname": "databricks_server_hostname",
            "http_path": "databricks_http_path",
            "token": "databricks_token",
            "metrics_table": "databricks_job_cluster_metrics_table",
        }
        for src, dst in mapping.items():
            if src in db:
                flat[dst] = db[src]

    pg = data.get("postgres") or {}
    if isinstance(pg, dict):
        for k in (
            "host",
            "port",
            "user",
            "password",
            "database",
            "ssl_mode",
        ):
            if k in pg:
                flat[f"postgres_{k}" if k != "database" else "postgres_database"] = pg[k]

    ao = data.get("azure_openai") or {}
    if isinstance(ao, dict):
        mapping = {
            "endpoint": "azure_openai_endpoint",
            "api_key": "azure_openai_api_key",
            "access_token": "azure_openai_access_token",
            "api_version": "azure_openai_api_version",
            "deployment": "azure_openai_deployment_name",
            "embedding_deployment": "azure_openai_embedding_deployment",
        }
        for src, dst in mapping.items():
            if src in ao:
                flat[dst] = ao[src]

    search = data.get("azure_search") or {}
    if isinstance(search, dict):
        for src, dst in {
            "endpoint": "azure_search_endpoint",
            "api_key": "azure_search_api_key",
            "index_name": "azure_search_index_name",
        }.items():
            if src in search:
                flat[dst] = search[src]

    storage = data.get("azure_storage") or {}
    if isinstance(storage, dict):
        for src, dst in {
            "account": "azure_storage_account",
            "key": "azure_storage_key",
            "container": "azure_storage_container",
        }.items():
            if src in storage:
                flat[dst] = storage[src]

    if "azure_key_vault_name" in data:
        flat["azure_key_vault_name"] = data["azure_key_vault_name"]

    vr = data.get("vector_retrieval") or {}
    if isinstance(vr, dict):
        if "backend" in vr:
            flat["vector_retrieval_backend"] = vr["backend"]
        if "faiss_index_path" in vr:
            flat["faiss_index_path"] = vr["faiss_index_path"]

    return {k: v for k, v in flat.items() if v is not None}


def flatten_agent_yaml(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map agent YAML overlays to flat Settings field names."""
    flat: Dict[str, Any] = {}
    llm = data.get("llm") or {}
    if isinstance(llm, dict):
        if "deployment" in llm:
            flat["azure_openai_deployment_name"] = llm["deployment"]
        if "embedding_deployment" in llm:
            flat["azure_openai_embedding_deployment"] = llm["embedding_deployment"]
        if "api_version" in llm:
            flat["azure_openai_api_version"] = llm["api_version"]
        if "default_model_name" in llm:
            flat["default_model_name"] = llm["default_model_name"]
        if "temperature" in llm:
            flat["llm_temperature"] = llm["temperature"]
        if "top_p" in llm:
            flat["llm_top_p"] = llm["top_p"]
        if "sizing_temperature" in llm:
            flat["sizing_llm_temperature"] = llm["sizing_temperature"]
        if "sizing_top_p" in llm:
            flat["sizing_llm_top_p"] = llm["sizing_top_p"]
        if "explanation_temperature" in llm:
            flat["explanation_llm_temperature"] = llm["explanation_temperature"]
        if "explanation_top_p" in llm:
            flat["explanation_llm_top_p"] = llm["explanation_top_p"]

    rag = data.get("rag") or {}
    if isinstance(rag, dict):
        if "backend" in rag:
            flat["vector_retrieval_backend"] = rag["backend"]
        if "enabled" in rag and rag["enabled"] is False:
            flat["vector_retrieval_backend"] = "none"
        if "top_k_recommendations" in rag:
            flat["rag_top_k_recommendations"] = rag["top_k_recommendations"]
        if "top_k_jobs" in rag:
            flat["rag_top_k_jobs"] = rag["top_k_jobs"]

    sizing = data.get("sizing") or {}
    if isinstance(sizing, dict):
        mapping = {
            "recommendation_auto_termination_minutes": "recommendation_auto_termination_minutes",
            "cost_retry_enabled": "recommendation_cost_retry_enabled",
            "default_confidence_score": "default_confidence_score",
            "default_monthly_budget": "default_monthly_budget",
        }
        for src, dst in mapping.items():
            if src in sizing:
                flat[dst] = sizing[src]

    guardrails = data.get("guardrails") or {}
    if isinstance(guardrails, dict):
        mapping = {
            "max_job_id_length": "guardrail_max_job_id_length",
            "max_date_range_days": "guardrail_max_date_range_days",
            "supported_intent": "guardrail_supported_intent",
        }
        for src, dst in mapping.items():
            if src in guardrails:
                flat[dst] = guardrails[src]

    return flat
