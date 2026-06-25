from uuid import uuid4

from shared.config.workspace_settings_resolver import resolve_workspace_agent_settings


def _llm_connection(conn_id: str) -> dict:
    return {
        "id": conn_id,
        "connection_type": "ai_foundry",
        "config": {
            "azure_openai_endpoint": "https://my-openai.openai.azure.com/",
            "azure_openai_deployment_name": "gpt-4o",
        },
    }


def test_resolve_local_csv_metrics_dataset():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    flat, secrets = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id},
        agent_settings={},
        connections=[_llm_connection(llm_id)],
        metrics_dataset={
            "id": metrics_id,
            "schema_profile": "job_cluster_metrics",
            "source_type": "local_csv",
            "local_path": "data/sample_job_metrics.csv",
        },
    )
    assert flat["use_local_data"] is True
    assert flat["local_data_path"] == "data/sample_job_metrics.csv"
    assert flat["azure_openai_deployment_name"] == "gpt-4o"
    assert secrets == {}


def test_resolve_databricks_metrics_dataset_with_env_wh():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    flat, _ = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id},
        agent_settings={},
        connections=[_llm_connection(llm_id)],
        metrics_dataset={
            "id": metrics_id,
            "schema_profile": "job_cluster_metrics",
            "source_type": "databricks_delta",
            "table_fqn": "dim_dev.dde_metrics.job_cluster_metrics",
        },
        metrics_wh_config={
            "databricks_server_hostname": "adb.example.net",
            "databricks_http_path": "/sql/1.0/warehouses/x",
        },
    )
    assert flat["use_local_data"] is False
    assert flat["databricks_server_hostname"] == "adb.example.net"
    assert flat["databricks_job_cluster_metrics_table"] == "dim_dev.dde_metrics.job_cluster_metrics"


def test_resolve_no_rag_binding_disables_search():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    flat, _ = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id},
        agent_settings={},
        connections=[_llm_connection(llm_id)],
        metrics_dataset={
            "id": metrics_id,
            "schema_profile": "job_cluster_metrics",
            "source_type": "local_csv",
            "local_path": "data/sample_job_metrics.csv",
        },
    )
    assert flat["vector_retrieval_backend"] == "none"


def test_resolve_ai_search_rag():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    rag_id = str(uuid4())
    flat, _ = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id, "rag": rag_id},
        agent_settings={},
        connections=[
            _llm_connection(llm_id),
            {
                "id": rag_id,
                "connection_type": "ai_search",
                "config": {
                    "azure_search_endpoint": "https://search.example.net",
                    "azure_search_index_name": "idx",
                },
            },
        ],
        metrics_dataset={
            "id": metrics_id,
            "schema_profile": "job_cluster_metrics",
            "source_type": "local_csv",
            "local_path": "data/sample_job_metrics.csv",
        },
    )
    assert flat["vector_retrieval_backend"] == "azure_search"
    assert flat["azure_search_index_name"] == "idx"
