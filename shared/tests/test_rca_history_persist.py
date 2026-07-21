"""RCA persistence uses recommendations_history."""

import os
from uuid import uuid4

os.environ["USE_POSTGRES"] = "false"

from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.services.rca_analysis_service import RcaAnalysisService, reset_rca_store_for_tests


def setup_function():
    reset_rca_store_for_tests()


def test_rca_save_and_get_by_run_memory():
    svc = RcaAnalysisService()
    request_id = uuid4()
    result = {
        "request_id": str(request_id),
        "job_id": "job-001",
        "job_run_id": "jr-001-002",
        "workspace_id": "ws-1",
        "root_cause": {
            "category": "OOM",
            "summary": "Executor OOM",
            "confidence": 0.9,
        },
        "recommended_actions": ["Increase memory"],
    }
    saved = svc.save(result=result, trigger_source="ui", agent_id=SPARK_JOB_RCA_AGENT_ID)
    assert saved.job_run_id == "jr-001-002"
    assert saved.agent_id == SPARK_JOB_RCA_AGENT_ID
    assert saved.category == "OOM"

    cached = svc.get_by_run("jr-001-002")
    assert cached is not None
    assert cached.request_id == saved.request_id

    listed = svc.list_for_job("job-001", workspace_id="ws-1")
    assert len(listed) == 1
    assert listed[0].summary == "Executor OOM"
