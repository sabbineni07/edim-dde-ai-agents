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

# Internal purpose derived from connection type (not shown in UI).
CONNECTION_TYPE_PURPOSE: Dict[str, str] = {
    "databricks": "metrics",
    "local_dataset": "metrics",
    "ai_foundry": "llm",
    "ai_search": "rag",
    "faiss": "rag",
}

_AUTH_MI = (
    "Authentication uses your Azure identity (az login or Managed Identity). "
    "No passwords or tokens are stored in this app — the API obtains them at runtime."
)

CONNECTION_TYPE_UI: Dict[str, Dict[str, Any]] = {
    "databricks": {
        "label": "Databricks",
        "description": "SQL warehouse endpoint for querying Unity Catalog tables in this environment.",
        "fields": [
            {
                "key": "databricks_server_hostname",
                "label": "Server hostname",
                "type": "string",
                "required": True,
                "placeholder": "adb-1234567890123456.7.azuredatabricks.net",
                "help": "Workspace URL host from Databricks → SQL warehouses.",
            },
            {
                "key": "databricks_http_path",
                "label": "SQL warehouse HTTP path",
                "type": "string",
                "required": True,
                "placeholder": "/sql/1.0/warehouses/xxxxxxxxxxxx",
                "help": "Connection details → HTTP path for your SQL warehouse.",
            },
        ],
        "auth_note": _AUTH_MI,
    },
    "local_dataset": {
        "label": "Local dataset",
        "description": "Sample CSV metrics for local development (no Azure required).",
        "fields": [
            {
                "key": "local_data_path",
                "label": "CSV file path",
                "type": "string",
                "required": True,
                "placeholder": "/app/data/sample_job_metrics.csv",
                "help": "Path inside the API container or on the host when running locally.",
            },
        ],
        "auth_note": "",
    },
    "ai_foundry": {
        "label": "Azure OpenAI / AI Foundry",
        "description": "Chat and embedding models for agent recommendations.",
        "fields": [
            {
                "key": "azure_openai_endpoint",
                "label": "Endpoint URL",
                "type": "string",
                "required": True,
                "placeholder": "https://my-openai.openai.azure.com/",
            },
            {
                "key": "azure_openai_deployment_name",
                "label": "Chat deployment",
                "type": "string",
                "required": True,
                "placeholder": "gpt-4o",
            },
            {
                "key": "azure_openai_embedding_deployment",
                "label": "Embedding deployment",
                "type": "string",
                "required": False,
                "placeholder": "text-embedding-3-small",
            },
        ],
        "auth_note": _AUTH_MI,
    },
    "ai_search": {
        "label": "Azure AI Search",
        "description": "Vector index for retrieval-augmented recommendations.",
        "fields": [
            {
                "key": "azure_search_endpoint",
                "label": "Search endpoint",
                "type": "string",
                "required": True,
                "placeholder": "https://my-search.search.windows.net",
            },
            {
                "key": "azure_search_index_name",
                "label": "Index name",
                "type": "string",
                "required": True,
            },
        ],
        "auth_note": _AUTH_MI,
    },
    "faiss": {
        "label": "FAISS (local index)",
        "description": "On-disk vector index for RAG (no cloud service).",
        "fields": [
            {
                "key": "faiss_index_path",
                "label": "Index path",
                "type": "string",
                "required": True,
                "placeholder": "/app/data/faiss_index",
            },
        ],
        "auth_note": "",
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
                "auth_note": meta.get("auth_note", ""),
            }
        )
    return out


def purpose_for_connection_type(connection_type: str) -> str:
    """Map connection type to internal purpose (metrics, llm, rag)."""
    purpose = CONNECTION_TYPE_PURPOSE.get(connection_type)
    if not purpose:
        raise ValueError(f"Unknown connection_type: {connection_type}")
    return purpose


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
    return clean
