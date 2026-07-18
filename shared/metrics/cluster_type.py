"""Cluster topology helpers for browse / UI metrics."""

from __future__ import annotations

from typing import Any, Optional

CLUSTER_TYPE_SINGLE_NODE = "single_node"
CLUSTER_TYPE_MULTI_NODE = "multi_node"


def infer_cluster_type(
    *,
    azure_worker_vm_size: Optional[str] = None,
    max_worker_nodes_provisioned: Optional[int] = None,
) -> str:
    """Return ``single_node`` when the job appears driver-only in browse data."""
    worker_vm = (azure_worker_vm_size or "").strip()
    max_workers = int(max_worker_nodes_provisioned or 1)
    if not worker_vm and max_workers <= 1:
        return CLUSTER_TYPE_SINGLE_NODE
    return CLUSTER_TYPE_MULTI_NODE


def cluster_type_from_row(row: dict[str, Any]) -> str:
    """Infer cluster type from a job summary or metrics row."""
    explicit = (row.get("cluster_type") or "").strip()
    if explicit in (CLUSTER_TYPE_SINGLE_NODE, CLUSTER_TYPE_MULTI_NODE):
        return explicit
    return infer_cluster_type(
        azure_worker_vm_size=row.get("azure_worker_vm_size"),
        max_worker_nodes_provisioned=row.get("max_worker_nodes_provisioned"),
    )
