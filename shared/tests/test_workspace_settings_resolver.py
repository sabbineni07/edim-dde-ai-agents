from uuid import uuid4

from shared.config.workspace_settings_resolver import resolve_workspace_agent_settings


def test_resolve_local_dataset_metrics():
    cid = str(uuid4())
    flat, secrets = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": cid},
        agent_settings={},
        connections=[
            {
                "id": cid,
                "connection_type": "local_dataset",
                "config": {"local_data_path": "data/sample_job_metrics.csv"},
            }
        ],
    )
    assert flat["use_local_data"] is True
    assert flat["local_data_path"] == "data/sample_job_metrics.csv"
    assert secrets == {}


def test_resolve_ai_search_rag():
    metrics_id = str(uuid4())
    rag_id = str(uuid4())
    flat, _ = resolve_workspace_agent_settings(
        agent_id="dbx_cluster_tuning_agent",
        bindings={"metrics": metrics_id, "rag": rag_id},
        agent_settings={},
        connections=[
            {
                "id": metrics_id,
                "connection_type": "local_dataset",
                "config": {"local_data_path": "data/sample_job_metrics.csv"},
            },
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
