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


def test_resolve_local_dataset_metrics():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    flat, secrets = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id},
        agent_settings={},
        connections=[
            {
                "id": metrics_id,
                "connection_type": "local_dataset",
                "config": {"local_data_path": "data/sample_job_metrics.csv"},
            },
            _llm_connection(llm_id),
        ],
    )
    assert flat["use_local_data"] is True
    assert flat["local_data_path"] == "data/sample_job_metrics.csv"
    assert flat["azure_openai_deployment_name"] == "gpt-4o"
    assert secrets == {}


def test_resolve_ai_search_rag():
    metrics_id = str(uuid4())
    llm_id = str(uuid4())
    rag_id = str(uuid4())
    flat, _ = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "llm": llm_id, "rag": rag_id},
        agent_settings={},
        connections=[
            {
                "id": metrics_id,
                "connection_type": "local_dataset",
                "config": {"local_data_path": "data/sample_job_metrics.csv"},
            },
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
    )
    assert flat["vector_retrieval_backend"] == "azure_search"
    assert flat["azure_search_index_name"] == "idx"
