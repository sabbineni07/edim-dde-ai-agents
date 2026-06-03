"""Connection type catalog and UI field metadata (no secrets)."""

from __future__ import annotations

from typing import Any, Dict, List

CONNECTION_TYPES = (
    "databricks",
    "local_dataset",
    "ai_foundry",
    "ai_search",
    "faiss",
)

CONNECTION_TYPE_UI: Dict[str, Dict[str, Any]] = {
    "databricks": {
        "label": "Databricks",
        "description": "Metrics and job runs from Databricks SQL.",
        "fields": [
            {
                "key": "databricks_server_hostname",
                "label": "Server hostname",
                "type": "string",
                "required": True,
            },
            {
                "key": "databricks_http_path",
                "label": "HTTP path (SQL warehouse)",
                "type": "string",
                "required": True,
            },
            {
                "key": "databricks_job_cluster_metrics_table",
                "label": "Job cluster metrics table",
                "type": "string",
                "required": True,
            },
            {
                "key": "credential_env_prefix",
                "label": "Credential env prefix (optional)",
                "type": "string",
                "placeholder": "CONN_<id>_",
                "required": False,
            },
        ],
        "credential_hints": [
            "{prefix}DATABRICKS_TOKEN — if unset, Managed Identity is used",
        ],
    },
    "local_dataset": {
        "label": "Local dataset",
        "description": "CSV or local metrics file for development.",
        "fields": [
            {
                "key": "local_data_path",
                "label": "Local data path",
                "type": "string",
                "required": True,
            },
        ],
        "credential_hints": [],
    },
    "ai_foundry": {
        "label": "AI Foundry / Azure OpenAI",
        "description": "LLM and embedding deployments.",
        "fields": [
            {
                "key": "azure_openai_endpoint",
                "label": "Endpoint",
                "type": "string",
                "required": True,
            },
            {
                "key": "azure_openai_deployment_name",
                "label": "Chat deployment",
                "type": "string",
                "required": True,
            },
            {
                "key": "azure_openai_embedding_deployment",
                "label": "Embedding deployment",
                "type": "string",
                "required": False,
            },
            {
                "key": "azure_openai_api_version",
                "label": "API version",
                "type": "string",
                "required": False,
            },
            {
                "key": "credential_env_prefix",
                "label": "Credential env prefix (optional)",
                "type": "string",
                "required": False,
            },
        ],
        "credential_hints": [
            "{prefix}AZURE_OPENAI_API_KEY or {prefix}AZURE_OPENAI_ACCESS_TOKEN — else Managed Identity",
        ],
    },
    "ai_search": {
        "label": "Azure AI Search",
        "description": "Vector retrieval for RAG.",
        "fields": [
            {
                "key": "azure_search_endpoint",
                "label": "Search endpoint",
                "type": "string",
                "required": True,
            },
            {
                "key": "azure_search_index_name",
                "label": "Index name",
                "type": "string",
                "required": True,
            },
            {
                "key": "credential_env_prefix",
                "label": "Credential env prefix (optional)",
                "type": "string",
                "required": False,
            },
        ],
        "credential_hints": ["{prefix}AZURE_SEARCH_API_KEY — else Managed Identity"],
    },
    "faiss": {
        "label": "FAISS (local index)",
        "description": "On-disk vector index for RAG.",
        "fields": [
            {"key": "faiss_index_path", "label": "Index path", "type": "string", "required": True},
        ],
        "credential_hints": [],
    },
}


def list_connection_types() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in CONNECTION_TYPES:
        meta = CONNECTION_TYPE_UI.get(t, {})
        out.append(
            {
                "connection_type": t,
                "label": meta.get("label", t),
                "description": meta.get("description", ""),
                "fields": meta.get("fields", []),
                "credential_hints": meta.get("credential_hints", []),
            }
        )
    return out


def validate_connection_config(connection_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    if connection_type not in CONNECTION_TYPES:
        raise ValueError(f"Unknown connection_type: {connection_type}")
    meta = CONNECTION_TYPE_UI[connection_type]
    clean: Dict[str, Any] = {}
    for field in meta.get("fields", []):
        key = field["key"]
        val = config.get(key)
        if field.get("required") and (val is None or str(val).strip() == ""):
            raise ValueError(f"Missing required field: {key}")
        if val is not None and str(val).strip() != "":
            clean[key] = val
    # Allow optional credential_env_prefix even if not in fields for type without it in required set
    if "credential_env_prefix" in config and config["credential_env_prefix"]:
        clean["credential_env_prefix"] = str(config["credential_env_prefix"]).strip()
    return clean
