"""Initial platform environment rows — used only to seed an empty database.

Environment ``id`` values (e.g. dim_dev, dim_uat) are stable business slugs tied to
Unity Catalog scope — not auto-generated UUIDs. Connection rows use UUID primary keys.
"""

from __future__ import annotations

from typing import Any, Dict, List

PLATFORM_ENVIRONMENT_SEED: List[Dict[str, Any]] = [
    {
        "id": "dim_dev",
        "code": "dim_dev",
        "display_name": "Development",
        "description": "All DEV workspaces in the tenant (Unity Catalog: dim_dev).",
        "environment_tier": "DEV",
        "source_type": "databricks_uc",
        "catalog_name": "dim_dev",
        "schema_name": "dde_metrics",
        "table_name": "job_cluster_metrics",
        "sort_order": 10,
        "icon": "code-slash",
    },
    {
        "id": "dim_uat",
        "code": "dim_uat",
        "display_name": "UAT",
        "description": "All UAT workspaces in the tenant (Unity Catalog: dim_uat).",
        "environment_tier": "UAT",
        "source_type": "databricks_uc",
        "catalog_name": "dim_uat",
        "schema_name": "dde_metrics",
        "table_name": "job_cluster_metrics",
        "sort_order": 20,
        "icon": "check2-circle",
    },
    {
        "id": "dim_intg",
        "code": "dim_intg",
        "display_name": "Integration",
        "description": "All INTG workspaces in the tenant (Unity Catalog: dim_intg).",
        "environment_tier": "INTG",
        "source_type": "databricks_uc",
        "catalog_name": "dim_intg",
        "schema_name": "dde_metrics",
        "table_name": "job_cluster_metrics",
        "sort_order": 30,
        "icon": "diagram-3",
    },
    {
        "id": "dim_prod",
        "code": "dim_prod",
        "display_name": "Production",
        "description": "All workspaces across tiers and business units (Unity Catalog: dim_prod).",
        "environment_tier": "PROD",
        "source_type": "databricks_uc",
        "catalog_name": "dim_prod",
        "schema_name": "dde_metrics",
        "table_name": "job_cluster_metrics",
        "sort_order": 40,
        "icon": "shield-check",
    },
    {
        "id": "sdbx",
        "code": "sdbx",
        "display_name": "SDBX",
        "description": "SDBX sandbox (Unity Catalog: dim_sdbx).",
        "environment_tier": "SDBX",
        "source_type": "databricks_uc",
        "catalog_name": "dim_sdbx",
        "schema_name": "dde_metrics",
        "table_name": "job_cluster_metrics",
        "sort_order": 50,
        "icon": "box-seam",
    },
    {
        "id": "local",
        "code": "local",
        "display_name": "Local (sample CSV)",
        "description": "Upload a CSV using the agent template, or use the bundled sample.",
        "environment_tier": "LOCAL",
        "source_type": "local_csv",
        "sort_order": 99,
        "icon": "file-earmark-spreadsheet",
    },
]
