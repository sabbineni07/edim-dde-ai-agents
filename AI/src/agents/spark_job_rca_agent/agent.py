"""Spark job failure RCA agent — LangGraph collect → classify → synthesize → validate."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph

from AI.src.agents.spark_job_rca_agent.chains.rca import RcaSynthesisChain
from AI.src.core.registry import register_agent
from AI.src.core.utils.token_usage import TokenUsageTracker
from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.config.settings import Settings
from shared.factories.spark_telemetry_factory import get_spark_telemetry_collector
from shared.rca.classify import classification_hint_text, classify_failure
from shared.rca.validate import build_rca_response, validate_rca_llm_output
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import CostLogger

logger = get_logger(__name__)

AGENT_ID = SPARK_JOB_RCA_AGENT_ID


class RcaState(TypedDict, total=False):
    request_id: str
    job_id: Optional[str]
    job_run_id: str
    job_run_date: Optional[str]
    task_key: Optional[str]
    workspace_id: Optional[str]
    evidence_pack_override: Optional[Dict[str, Any]]
    evidence_pack: Dict[str, Any]
    classification_hint: Dict[str, Any]
    llm_raw: Dict[str, Any]
    validated: Dict[str, Any]
    result: Dict[str, Any]
    token_tracker: Any


def _register_spark_job_rca_agent(cls):
    from AI.src.agents.spark_job_rca_agent.deps import get_spark_job_rca_agent_deps

    return register_agent(
        AGENT_ID,
        deps_factory=get_spark_job_rca_agent_deps,
    )(cls)


@_register_spark_job_rca_agent
class SparkJobRcaAgent:
    """Root-cause analysis for a failed Spark job run from logs + metrics."""

    agent_id = AGENT_ID

    def __init__(
        self,
        rca_chain: RcaSynthesisChain,
        settings: Optional[Settings] = None,
        cost_logger: Optional["CostLogger"] = None,
        telemetry_collector: Any = None,
    ):
        self.rca_chain = rca_chain
        self.settings = settings
        self.cost_logger = cost_logger
        self._telemetry_collector = telemetry_collector
        self._graph = self._build_graph()

    def _collector(self):
        if self._telemetry_collector is not None:
            return self._telemetry_collector
        return get_spark_telemetry_collector(self.settings)

    def _collect_evidence(self, state: RcaState) -> Dict[str, Any]:
        if state.get("evidence_pack_override"):
            return {"evidence_pack": state["evidence_pack_override"]}
        pack = self._collector().build_evidence_pack_for_run(
            job_run_id=state["job_run_id"],
            job_id=state.get("job_id"),
            job_run_date=state.get("job_run_date"),
            task_key=state.get("task_key"),
            workspace_id=state.get("workspace_id"),
        )
        return {"evidence_pack": pack}

    def _rule_classify(self, state: RcaState) -> Dict[str, Any]:
        hint = classify_failure(state.get("evidence_pack") or {})
        return {"classification_hint": hint}

    def _llm_rca(self, state: RcaState) -> Dict[str, Any]:
        hint = state.get("classification_hint") or {}
        raw = self.rca_chain.invoke(
            evidence_pack=state.get("evidence_pack") or {},
            classification_hint=classification_hint_text(hint),
            token_tracker=state.get("token_tracker"),
        )
        return {"llm_raw": raw}

    def _validate_output(self, state: RcaState) -> Dict[str, Any]:
        validated = validate_rca_llm_output(
            state.get("llm_raw") or {},
            evidence_pack=state.get("evidence_pack") or {},
            classification_hint=state.get("classification_hint") or {},
        )
        request_id = UUID(state["request_id"]) if state.get("request_id") else uuid4()
        result = build_rca_response(
            request_id=request_id,
            job_id=state.get("job_id") or (state.get("evidence_pack") or {}).get("job_id"),
            job_run_id=state["job_run_id"],
            task_key=state.get("task_key"),
            validated=validated,
        )
        return {"validated": validated, "result": result}

    def _build_graph(self):
        g = StateGraph(RcaState)
        g.add_node("collect_evidence", self._collect_evidence)
        g.add_node("rule_classify", self._rule_classify)
        g.add_node("llm_rca", self._llm_rca)
        g.add_node("validate_output", self._validate_output)
        g.set_entry_point("collect_evidence")
        g.add_edge("collect_evidence", "rule_classify")
        g.add_edge("rule_classify", "llm_rca")
        g.add_edge("llm_rca", "validate_output")
        g.add_edge("validate_output", END)
        return g.compile()

    def analyze(
        self,
        *,
        job_run_id: str,
        job_id: Optional[str] = None,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
        request_id: Optional[UUID] = None,
        evidence_pack_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rid = request_id or uuid4()
        tracker = TokenUsageTracker()
        initial: RcaState = {
            "request_id": str(rid),
            "job_id": job_id,
            "job_run_id": job_run_id,
            "job_run_date": job_run_date,
            "task_key": task_key,
            "workspace_id": workspace_id,
            "evidence_pack_override": evidence_pack_override,
            "token_tracker": tracker,
        }
        logger.info(
            "spark_rca_analyze_start",
            job_run_id=job_run_id,
            job_id=job_id,
            task_key=task_key,
            request_id=str(rid),
        )
        final = self._graph.invoke(initial)
        result = final.get("result") or {}
        token_usage = tracker.get_summary() if hasattr(tracker, "get_summary") else None
        if token_usage:
            result = {**result, "token_usage_analysis": token_usage}
        if self.cost_logger and token_usage:
            try:
                breakdown = (token_usage.get("cost_estimate") or {}).get("breakdown_by_chain") or {}
                for chain_name, chain_data in breakdown.items():
                    self.cost_logger.log_token_usage(
                        request_id=rid,
                        model_name=str(chain_data.get("model") or "gpt-4o"),
                        chain_name=str(chain_name),
                        input_tokens=int(chain_data.get("input_tokens") or 0),
                        output_tokens=int(chain_data.get("output_tokens") or 0),
                        total_tokens=int(chain_data.get("input_tokens") or 0)
                        + int(chain_data.get("output_tokens") or 0),
                        cost_usd=float(chain_data.get("total_cost_usd") or 0.0),
                        job_id=job_id,
                        workspace_id=workspace_id,
                    )
            except Exception as e:
                logger.debug("rca_cost_log_skipped", error=str(e))
        logger.info(
            "spark_rca_analyze_complete",
            request_id=str(rid),
            category=(result.get("root_cause") or {}).get("category"),
        )
        return result
