"""Chat API over job cost and cluster metrics."""

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from AI.src.services.azure_openai_service import AzureOpenAINotConfiguredError, AzureOpenAIService
from DE.src.processors.metrics_processor import MetricsProcessor
from shared.factories.data_collector_factory import get_data_collector
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    question: str
    workspace_id: Optional[str] = None
    job_id: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ChatResponse(BaseModel):
    answer: str
    context_summary: Dict[str, Any]


def _default_date_range(req: ChatRequest) -> Dict[str, str]:
    today = date.today()
    end_date = req.end_date or today
    start_date = req.start_date or (end_date - timedelta(days=30))
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )
    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
    }


@router.post("/", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Chat endpoint that answers questions using job cost and cluster metrics.

    This is intentionally simple for now: it pulls recent aggregated job metrics
    (and optionally narrows to a workspace/job), summarizes them, and passes both
    the metrics summary and the user's question to the LLM.
    """
    dr = _default_date_range(req)
    collector = get_data_collector()

    try:
        metrics = collector.collect_job_cluster_metrics(
            start_date=dr["start_date"],
            end_date=dr["end_date"],
            job_ids=[req.job_id] if req.job_id else None,
            workspace_id=req.workspace_id,
        )
    except Exception as e:
        logger.error("chat_collect_metrics_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to read job metrics") from e

    processor = MetricsProcessor()
    aggregated: Dict[str, Dict[str, Any]] = {}
    if metrics:
        aggregated = processor.aggregate_by_job(metrics)

    # Build a compact summary to send to the LLM
    jobs_summary: List[Dict[str, Any]] = []
    for job_id, agg in aggregated.items():
        jobs_summary.append(
            {
                "job_id": job_id,
                "job_name": agg.get("job_name"),
                "workspace_id": req.workspace_id,
                "workload_type": agg.get("workload_type"),
                "avg_cpu_utilization_pct": agg.get("avg_cpu_utilization"),
                "avg_memory_utilization_pct": agg.get("avg_memory_utilization"),
                "avg_duration_seconds": agg.get("avg_duration_seconds"),
                "total_runs": agg.get("total_runs"),
                "current_node_type": agg.get("current_node_type"),
                "current_min_workers": agg.get("current_min_workers"),
                "current_max_workers": agg.get("current_max_workers"),
                "last_run_date": agg.get("last_run_date"),
            }
        )

    try:
        aos = AzureOpenAIService()
        llm = aos.get_llm()
    except AzureOpenAINotConfiguredError as e:
        logger.error("chat_azure_not_configured", error=str(e))
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.error("chat_azure_init_error", error=str(e))
        raise HTTPException(status_code=500, detail="LLM not available") from e

    system_prompt = (
        "You are an assistant that answers questions about Databricks job cost and "
        "cluster metrics. Use only the metrics summary provided. When you talk about "
        "specific jobs, cite job_id and any relevant utilization or cost numbers."
    )
    user_content = (
        f"Date range: {dr['start_date']} to {dr['end_date']}\n"
        f"Workspace: {req.workspace_id or 'ALL'}\n"
        f"Job filter: {req.job_id or 'ALL'}\n\n"
        f"Job metrics summary (JSON): {jobs_summary}\n\n"
        f"User question: {req.question}"
    )

    try:
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )
        answer_text = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        logger.error("chat_llm_error", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate answer") from e

    return ChatResponse(
        answer=answer_text,
        context_summary={
            "workspace_id": req.workspace_id,
            "job_id": req.job_id,
            "start_date": dr["start_date"],
            "end_date": dr["end_date"],
            "job_count": len(jobs_summary),
        },
    )
