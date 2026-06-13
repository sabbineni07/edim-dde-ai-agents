"""Workspace agent settings resolution with dataset metrics binding."""

import os

import pytest

os.environ.setdefault("USE_POSTGRES", "false")

from shared.services.environment_connection_service import (
    reset_environment_connection_store_for_tests,
)
from shared.services.environment_dataset_service import reset_environment_dataset_store_for_tests
from shared.services.platform_environment_service import reset_platform_environment_store_for_tests
from shared.services.workspace_agent_service import (
    WorkspaceAgentService,
    reset_workspace_agent_store_for_tests,
)

ENV = "dim_dev"
WS = "1234567890123456"


@pytest.fixture(autouse=True)
def _reset_stores():
    reset_platform_environment_store_for_tests()
    reset_environment_connection_store_for_tests()
    reset_environment_dataset_store_for_tests()
    reset_workspace_agent_store_for_tests()


def test_resolve_settings_uses_dataset_table_and_env_wh():
    conn_svc = __import__(
        "shared.services.environment_connection_service",
        fromlist=["EnvironmentConnectionService"],
    ).EnvironmentConnectionService()
    ds_svc = __import__(
        "shared.services.environment_dataset_service",
        fromlist=["EnvironmentDatasetService"],
    ).EnvironmentDatasetService()
    wa_svc = WorkspaceAgentService()

    wh = conn_svc.create_connection(
        environment_id=ENV,
        name="WH",
        connection_type="databricks",
        purpose="metrics",
        config={
            "databricks_server_hostname": "adb-1.azuredatabricks.net",
            "databricks_http_path": "/sql/1.0/warehouses/abc",
        },
        set_default=True,
    )
    llm = conn_svc.create_connection(
        environment_id=ENV,
        name="LLM",
        connection_type="ai_foundry",
        purpose="llm",
        config={
            "azure_openai_endpoint": "https://example.openai.azure.com/",
            "azure_openai_deployment_name": "gpt-4o",
        },
    )
    metrics_ds = ds_svc.create_dataset(
        environment_id=ENV,
        name="Job cluster metrics",
        source_type="databricks_delta",
        schema_profile="job_cluster_metrics",
        table_fqn="dim_dev.dde_metrics.job_cluster_metrics",
        set_default=True,
    )

    wa = wa_svc.create_agent(
        environment_id=ENV,
        workspace_id=WS,
        workspace_name="Test WS",
        agent_id="dbx_cluster_tuning_agent",
        name="Sizing",
        bindings={"metrics": str(metrics_ds.id), "llm": str(llm.id)},
    )

    _, flat, _ = wa_svc.resolve_settings_for_agent(wa.id)
    assert flat["databricks_server_hostname"] == "adb-1.azuredatabricks.net"
    assert flat["databricks_http_path"] == "/sql/1.0/warehouses/abc"
    assert flat["databricks_job_cluster_metrics_table"] == metrics_ds.table_fqn
    assert flat["azure_openai_endpoint"] == "https://example.openai.azure.com/"
    assert wh.id  # referenced via env default, not agent binding
