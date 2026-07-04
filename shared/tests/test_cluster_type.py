"""Tests for cluster topology inference."""

from shared.metrics.cluster_type import (
    CLUSTER_TYPE_MULTI_NODE,
    CLUSTER_TYPE_SINGLE_NODE,
    cluster_type_from_row,
    infer_cluster_type,
)


def test_infer_single_node_without_worker_vm():
    assert (
        infer_cluster_type(
            azure_worker_vm_size=None,
            max_worker_nodes_provisioned=1,
        )
        == CLUSTER_TYPE_SINGLE_NODE
    )


def test_infer_multi_node_with_worker_vm():
    assert (
        infer_cluster_type(
            azure_worker_vm_size="Standard_E8s_v3",
            max_worker_nodes_provisioned=1,
        )
        == CLUSTER_TYPE_MULTI_NODE
    )


def test_infer_multi_node_with_scaled_workers():
    assert (
        infer_cluster_type(
            azure_worker_vm_size=None,
            max_worker_nodes_provisioned=8,
        )
        == CLUSTER_TYPE_MULTI_NODE
    )


def test_cluster_type_from_row_prefers_explicit_value():
    assert cluster_type_from_row({"cluster_type": "single_node"}) == CLUSTER_TYPE_SINGLE_NODE
