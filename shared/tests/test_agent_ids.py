from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID


def test_canonical_agent_id():
    assert DBX_CLUSTER_TUNING_AGENT_ID == "dbx_cluster_tuning_agent"
