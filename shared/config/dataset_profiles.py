"""Dataset schema profiles and validation for environment-scoped datasets."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DATASET_SOURCE_TYPES = ("databricks_delta", "local_csv")

# Environment browse default (Workspaces / Jobs / Runs). Not for agent evidence.
BROWSE_SCHEMA_PROFILE = "job_inventory"

SCHEMA_PROFILES: Dict[str, Dict[str, Any]] = {
    "job_inventory": {
        "label": "Job inventory",
        "description": (
            "Browse inventory for Workspaces, Jobs, and Runs (environment default). "
            "Typically a UC view over job_cluster_metrics; may grow independently."
        ),
        "source_types": ["databricks_delta", "local_csv"],
    },
    "job_cluster_metrics": {
        "label": "Job cluster metrics",
        "description": (
            "Per-run Databricks cluster utilization for the Cluster Tuning agent. "
            "Not used as the environment browse default."
        ),
        "source_types": ["databricks_delta", "local_csv"],
    },
    "spark_logs": {
        "label": "Spark logs",
        "description": "Append-only operational Spark/application logs for pipeline runs (RCA evidence).",
        "source_types": ["databricks_delta", "local_csv"],
    },
    "spark_metrics": {
        "label": "Spark metrics",
        "description": (
            "Append-only Spark Connect telemetry — SQL, jobs, stages, pipeline lifecycle (RCA evidence)."
        ),
        "source_types": ["databricks_delta", "local_csv"],
    },
}


def is_browse_schema_profile(schema_profile: str) -> bool:
    return (schema_profile or "").strip() == BROWSE_SCHEMA_PROFILE


def require_browse_schema_profile(schema_profile: str) -> str:
    """Raise ValueError unless profile is the browse inventory profile."""
    key = (schema_profile or "").strip()
    if key != BROWSE_SCHEMA_PROFILE:
        raise ValueError(
            f"Environment browse default must use schema_profile "
            f"'{BROWSE_SCHEMA_PROFILE}' (got '{schema_profile or ''}'). "
            "Agent evidence datasets (job_cluster_metrics, spark_logs, spark_metrics) "
            "are bound on workspace agent installs, not as the browse default."
        )
    return key


def list_schema_profiles() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for profile_id, meta in SCHEMA_PROFILES.items():
        out.append(
            {
                "schema_profile": profile_id,
                "label": meta.get("label", profile_id),
                "description": meta.get("description", ""),
                "source_types": list(meta.get("source_types", [])),
                "is_browse_default": profile_id == BROWSE_SCHEMA_PROFILE,
            }
        )
    return out


def validate_schema_profile(schema_profile: str) -> str:
    key = (schema_profile or "").strip()
    if key not in SCHEMA_PROFILES:
        raise ValueError(f"Unknown schema_profile: {schema_profile}")
    return key


def validate_dataset_fields(
    *,
    source_type: str,
    schema_profile: str,
    table_fqn: Optional[str] = None,
    local_path: Optional[str] = None,
) -> Dict[str, Any]:
    st = (source_type or "").strip()
    if st not in DATASET_SOURCE_TYPES:
        raise ValueError(f"Unknown source_type: {source_type}")

    profile = validate_schema_profile(schema_profile)
    allowed = SCHEMA_PROFILES[profile].get("source_types", [])
    if st not in allowed:
        raise ValueError(f"schema_profile '{profile}' does not support source_type '{st}'")

    clean: Dict[str, Any] = {
        "source_type": st,
        "schema_profile": profile,
        "table_fqn": None,
        "local_path": None,
    }

    if st == "databricks_delta":
        fqn = (table_fqn or "").strip()
        if not fqn or fqn.count(".") < 2:
            raise ValueError("table_fqn is required (catalog.schema.table) for databricks_delta")
        clean["table_fqn"] = fqn
    elif st == "local_csv":
        path = (local_path or "").strip()
        if not path:
            raise ValueError("local_path is required for local_csv datasets")
        clean["local_path"] = path

    return clean
