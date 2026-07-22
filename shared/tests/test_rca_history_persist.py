"""RCA persistence uses recommendations_history."""

import os
from uuid import uuid4

os.environ["USE_POSTGRES"] = "false"

from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.recommendation_lifecycle import LIFECYCLE_RECOMMENDED, LIFECYCLE_REJECTED
from shared.services.rca_analysis_service import RcaAnalysisService, reset_rca_store_for_tests


def setup_function():
    reset_rca_store_for_tests()


def _result(job_run_id: str, summary: str, request_id=None):
    rid = request_id or uuid4()
    return {
        "request_id": str(rid),
        "job_id": "job-001",
        "job_run_id": job_run_id,
        "workspace_id": "ws-1",
        "root_cause": {
            "category": "resource",
            "summary": summary,
            "confidence": 0.9,
        },
        "recommended_actions": ["Increase memory"],
    }


def test_rca_save_and_get_by_run_memory():
    svc = RcaAnalysisService()
    request_id = uuid4()
    saved = svc.save(
        result=_result("jr-001-002", "Executor OOM", request_id),
        trigger_source="ui",
        agent_id=SPARK_JOB_RCA_AGENT_ID,
    )
    assert saved.job_run_id == "jr-001-002"
    assert saved.agent_id == SPARK_JOB_RCA_AGENT_ID
    assert saved.category == "resource"

    cached = svc.get_by_run("jr-001-002")
    assert cached is not None
    assert cached.request_id == saved.request_id

    listed = svc.list_for_job("job-001", workspace_id="ws-1")
    assert len(listed) == 1
    assert listed[0].summary == "Executor OOM"


def test_get_open_by_run_skips_terminal():
    svc = RcaAnalysisService()
    first = svc.save(result=_result("jr-open-1", "First"), force=True)
    assert svc.get_open_by_run("jr-open-1") is not None
    assert first.lifecycle_status == LIFECYCLE_RECOMMENDED

    # Mark memory row terminal (simulates reject/approve).
    from shared.services import rca_analysis_service as mod

    key = f"{SPARK_JOB_RCA_AGENT_ID}|jr-open-1|"
    mod._MEM_RCA[key]["lifecycle_status"] = LIFECYCLE_REJECTED

    assert svc.get_open_by_run("jr-open-1") is None
    assert svc.get_by_run("jr-open-1") is not None


def test_save_without_force_reuses_open_but_allows_after_terminal():
    svc = RcaAnalysisService()
    first = svc.save(result=_result("jr-reuse-1", "Open RCA"), force=False)
    second = svc.save(result=_result("jr-reuse-1", "Should not replace"), force=False)
    assert second.request_id == first.request_id
    assert second.summary == "Open RCA"

    from shared.services import rca_analysis_service as mod

    key = f"{SPARK_JOB_RCA_AGENT_ID}|jr-reuse-1|"
    mod._MEM_RCA[key]["lifecycle_status"] = LIFECYCLE_REJECTED

    third = svc.save(result=_result("jr-reuse-1", "Fresh after reject"), force=False)
    assert third.request_id != first.request_id
    assert third.summary == "Fresh after reject"


def test_save_force_inserts_new_while_open():
    svc = RcaAnalysisService()
    first = svc.save(result=_result("jr-force-1", "Original"), force=False)
    forced = svc.save(result=_result("jr-force-1", "Forced re-run"), force=True)
    assert forced.request_id != first.request_id
    assert forced.summary == "Forced re-run"
    assert svc.get_open_by_run("jr-force-1").request_id == forced.request_id
