"""Per job-run Databricks cluster utilization right-sizing agent."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph

from AI.src.agents.job_run_cluster_sizing.chains.explanation import RecommendationExplanationChain
from AI.src.agents.job_run_cluster_sizing.chains.sizing import (
    SIZING_RECOMMENDATION_KEYS,
    ClusterSizingChain,
    split_sizing_llm_response,
)
from AI.src.agents.job_run_cluster_sizing.tools.cost_calculator_tools import (
    calculate_cluster_cost,
    calculate_cost_savings,
)
from AI.src.agents.job_run_cluster_sizing.tools.databricks_tools import (
    get_cost_analysis,
    get_job_cluster_metrics,
)
from AI.src.agents.job_run_cluster_sizing.tools.validation_tools import (
    assess_risks,
    parse_vcpus_from_node_type,
    validate_performance,
)
from AI.src.core.registry import register_agent
from AI.src.core.utils.token_usage import TokenUsageTracker
from shared.config.loader import get_agent_settings
from shared.config.settings import Settings
from shared.guardrails import (
    NoJobMetricsError,
    build_guardrail_feedback,
    should_retry_cost_recommendation,
    validate_and_clamp_with_adjustments,
)
from shared.guardrails.sku_allowlist import nearest_allowed_node_type
from shared.models.job_run_ingest import default_sizing_policy, to_llm_ingest_dict
from shared.recommendation_output import build_recommendation_response_v2
from shared.sizing.policy import compute_sizing_hints, infer_reason_codes, sizing_hints_for_llm
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import CostLogger, SearchService

logger = get_logger(__name__)

AGENT_ID = "job_run_cluster_sizing"
DEPRECATED_AGENT_ID = "cluster_config"


class RecommendationState(TypedDict, total=False):
    job_id: str
    job_run_id: str
    start_date: str
    end_date: str
    include_explanation: bool
    job_run_ingest_override: Optional[Dict]
    job_cluster_metrics: Dict
    job_run_ingest: Dict
    sizing_hints: Dict
    resource_utilization: Dict
    cost_analysis: Dict
    pattern_analysis: str
    cost_optimization: Dict
    llm_recommendation: Dict
    guardrail_recommendation: Dict
    guardrail_adjustments: List[Dict]
    recommendation_attempts: int
    performance_validation: Dict
    risk_assessment: Dict
    recommendation: Dict
    explanation: str
    reason_codes: List[str]
    token_tracker: Any


def _register_job_run_cluster_sizing_agent(cls):
    from AI.src.agents.job_run_cluster_sizing.deps import get_job_run_cluster_sizing_deps

    return register_agent(
        AGENT_ID,
        deps_factory=get_job_run_cluster_sizing_deps,
        aliases=[DEPRECATED_AGENT_ID],
    )(cls)


@_register_job_run_cluster_sizing_agent
class JobRunClusterSizingAgent:
    """Recommend cluster right-sizing for a single Databricks job run."""

    agent_id = AGENT_ID

    def __init__(
        self,
        sizing_chain: ClusterSizingChain,
        explanation_chain: RecommendationExplanationChain,
        settings: Optional[Settings] = None,
        cost_logger: Optional["CostLogger"] = None,
        search_service: Optional["SearchService"] = None,
        cost_chain: Optional[ClusterSizingChain] = None,
        pattern_chain: Optional[Any] = None,
    ):
        self.sizing_chain = sizing_chain or cost_chain
        if self.sizing_chain is None:
            raise TypeError("sizing_chain is required")
        if pattern_chain is not None:
            logger.warning("pattern_chain_removed", detail="Use merged ClusterSizingChain only")
        self.explanation_chain = explanation_chain
        self.cost_logger = cost_logger
        self.search_service = search_service
        self.settings: Settings = settings or get_agent_settings(AGENT_ID)
        self.graph = self._create_recommendation_graph()
        logger.info("job_run_cluster_sizing_agent_initialized")

    def _ingest_from_state(self, state: RecommendationState) -> Dict:
        return state.get("job_run_ingest") or state.get("job_cluster_metrics") or {}

    def _create_recommendation_graph(self) -> StateGraph:
        sizing_chain = self.sizing_chain
        explanation_chain = self.explanation_chain
        model_name = self.settings.azure_openai_deployment_name or self.settings.default_model_name

        def collect_data(state: RecommendationState) -> RecommendationState:
            logger.info(
                "collecting_job_data",
                job_id=state["job_id"],
                job_run_id=state.get("job_run_id"),
            )
            override = state.get("job_run_ingest_override")
            if override:
                ingest = to_llm_ingest_dict(override)
                state["job_cluster_metrics"] = {**override, **ingest, "job_run_ingest": ingest}
            else:
                state["job_cluster_metrics"] = get_job_cluster_metrics.invoke(
                    {
                        "job_id": state["job_id"],
                        "job_run_id": state["job_run_id"],
                        "start_date": state["start_date"],
                        "end_date": state["end_date"],
                    }
                )
            jcm = state["job_cluster_metrics"]
            if not jcm or not isinstance(jcm, dict) or len(jcm) == 0:
                raise NoJobMetricsError(
                    job_id=state["job_id"],
                    start_date=state["start_date"],
                    end_date=state["end_date"],
                    job_run_id=state.get("job_run_id"),
                )
            ingest = jcm.get("job_run_ingest") or to_llm_ingest_dict(jcm)
            state["job_run_ingest"] = ingest
            policy = default_sizing_policy()
            state["sizing_hints"] = compute_sizing_hints(ingest, policy)
            state["resource_utilization"] = {
                "peak_cpu_utilization_pct": ingest.get("peak_cpu_utilization_pct", 0),
                "peak_memory_utilization_pct": ingest.get("peak_memory_utilization_pct", 0),
                "avg_worker_nodes_consumed": ingest.get("avg_worker_nodes_consumed", 0),
                "workflow_task_count": ingest.get("workflow_task_count", 0),
            }
            state["cost_analysis"] = get_cost_analysis.invoke(
                {
                    "job_id": state["job_id"],
                    "start_date": state["start_date"],
                    "end_date": state["end_date"],
                }
            )
            return state

        def run_cluster_sizing(state: RecommendationState) -> RecommendationState:
            ingest = self._ingest_from_state(state)
            hints = state.get("sizing_hints") or compute_sizing_hints(ingest)
            narrow_hints = sizing_hints_for_llm(hints)
            current_config = {
                "azure_worker_vm_size": ingest.get("azure_worker_vm_size", "Standard_E8s_v3"),
                "min_workers": ingest.get("current_min_workers", 1),
                "max_workers": ingest.get("max_worker_nodes_cluster_ceiling", 16),
            }
            attempts = 0
            llm_sizing: Dict = {}
            llm_rec: Dict = {}
            applied: Dict = {}
            adjustments: List[Dict] = []

            while attempts < 2:
                attempts += 1
                feedback = None
                if attempts > 1:
                    feedback = build_guardrail_feedback(adjustments, attempt=attempts)

                llm_sizing = sizing_chain.optimize(
                    current_config,
                    ingest,
                    narrow_hints,
                    guardrail_feedback=feedback,
                )
                pattern_text, llm_rec = split_sizing_llm_response(llm_sizing)
                state["pattern_analysis"] = pattern_text
                applied, adjustments = validate_and_clamp_with_adjustments(
                    llm_rec, job_run_ingest=ingest
                )

                if not (
                    self.settings.recommendation_cost_retry_enabled
                    and should_retry_cost_recommendation(
                        adjustments, attempt=attempts, max_attempts=2
                    )
                ):
                    break

            state["llm_recommendation"] = {
                k: llm_rec.get(k) for k in SIZING_RECOMMENDATION_KEYS if k in llm_rec
            }
            state["guardrail_recommendation"] = dict(applied)
            state["guardrail_adjustments"] = adjustments
            state["recommendation_attempts"] = attempts
            state["cost_optimization"] = applied
            if state.get("token_tracker"):
                state["token_tracker"].estimate_chain_usage(
                    chain_name="cluster_sizing",
                    model=model_name,
                    input_text={
                        "current_config": current_config,
                        "job_run_ingest": ingest,
                        "sizing_hints": narrow_hints,
                        "recommendation_attempts": attempts,
                    },
                    output_text=llm_sizing,
                )
            return state

        def validate_performance_node(state: RecommendationState) -> RecommendationState:
            ingest = self._ingest_from_state(state)
            ru = state["resource_utilization"]
            current_node_type = ingest.get("azure_worker_vm_size", "Standard_E8s_v3")
            current_vcpus = parse_vcpus_from_node_type(current_node_type)
            current_max_workers = int(ingest.get("max_worker_nodes_cluster_ceiling", 16))
            recommended_vcpus = state["cost_optimization"].get("vcpus", 8)
            recommended_max_workers = state["cost_optimization"].get("max_workers", 8)
            state["performance_validation"] = validate_performance.invoke(
                {
                    "current_peak_cpu": ru.get("peak_cpu_utilization_pct", 0),
                    "current_peak_memory": ru.get("peak_memory_utilization_pct", 0),
                    "recommended_vcpus": recommended_vcpus,
                    "recommended_max_workers": recommended_max_workers,
                    "current_vcpus": current_vcpus,
                    "current_max_workers": current_max_workers,
                    "job_run_ingest": ingest,
                }
            )
            return state

        def assess_risks_node(state: RecommendationState) -> RecommendationState:
            ingest = self._ingest_from_state(state)
            current_vcpus = parse_vcpus_from_node_type(
                ingest.get("azure_worker_vm_size", "Standard_E8s_v3")
            )
            current_max = int(ingest.get("max_worker_nodes_cluster_ceiling", 16))
            rec = state["cost_optimization"]
            current_capacity = current_max * current_vcpus
            recommended_capacity = rec.get("max_workers", 8) * rec.get("vcpus", 8)
            change_magnitude = (
                abs((current_capacity - recommended_capacity) / current_capacity * 100)
                if current_capacity > 0
                else 0
            )
            state["risk_assessment"] = assess_risks.invoke(
                {
                    "configuration_change_magnitude": change_magnitude,
                    "performance_validation": state["performance_validation"],
                    "cost_savings_pct": 0,
                }
            )
            return state

        def generate_recommendation(state: RecommendationState) -> RecommendationState:
            ingest = self._ingest_from_state(state)
            current_node_type = ingest.get("azure_worker_vm_size", "Standard_E8s_v3")
            co = state["cost_optimization"]
            recommended_node_type = co.get("azure_node_type") or nearest_allowed_node_type(
                co.get("node_family", "E"),
                co.get("vcpus", 8),
                current_node_type=current_node_type,
            )
            avg_nodes = float(ingest.get("avg_worker_nodes_consumed") or 4)
            current_cost = calculate_cluster_cost.invoke(
                {
                    "node_type": current_node_type,
                    "min_workers": ingest.get("current_min_workers", 1),
                    "max_workers": int(ingest.get("max_worker_nodes_cluster_ceiling", 16)),
                    "avg_nodes": avg_nodes,
                    "hours_per_month": 730,
                }
            )
            recommended_cost = calculate_cluster_cost.invoke(
                {
                    "node_type": recommended_node_type,
                    "min_workers": co["min_workers"],
                    "max_workers": co["max_workers"],
                    "avg_nodes": avg_nodes,
                    "hours_per_month": 730,
                }
            )
            savings = calculate_cost_savings.invoke(
                {
                    "current_cost": current_cost["monthly_cost"],
                    "recommended_cost": recommended_cost["monthly_cost"],
                }
            )
            state["recommendation"] = {
                **co,
                "node_type": recommended_node_type,
                "azure_node_type": recommended_node_type,
                "current_cost": current_cost["monthly_cost"],
                "recommended_cost": recommended_cost["monthly_cost"],
                "savings_usd": savings["savings_usd"],
                "savings_pct": savings["savings_pct"],
                "risk_level": state["risk_assessment"]["risk_level"],
                "confidence_score": self.settings.default_confidence_score,
            }
            change_required = recommended_node_type != current_node_type or co.get(
                "max_workers"
            ) != int(ingest.get("max_worker_nodes_cluster_ceiling", 16))
            state["reason_codes"] = infer_reason_codes(
                ingest, state["recommendation"], change_required=change_required
            )
            return state

        def generate_explanation_node(state: RecommendationState) -> RecommendationState:
            ingest = self._ingest_from_state(state)
            result = explanation_chain.explain(
                recommendation=state["recommendation"],
                job_run_ingest=ingest,
                pattern_analysis=state["pattern_analysis"],
                risk_assessment=state["risk_assessment"],
            )
            state["explanation"] = result
            if state.get("token_tracker"):
                state["token_tracker"].estimate_chain_usage(
                    chain_name="explanation",
                    model=model_name,
                    input_text=state["recommendation"],
                    output_text=result,
                )
            return state

        def route_after_recommendation(state: RecommendationState) -> str:
            if state.get("include_explanation", False):
                return "generate_explanation"
            return "done"

        workflow = StateGraph(RecommendationState)
        workflow.add_node("collect_data", collect_data)
        workflow.add_node("run_cluster_sizing", run_cluster_sizing)
        workflow.add_node("validate_performance", validate_performance_node)
        workflow.add_node("assess_risks", assess_risks_node)
        workflow.add_node("generate_recommendation", generate_recommendation)
        workflow.add_node("generate_explanation", generate_explanation_node)
        workflow.set_entry_point("collect_data")
        workflow.add_edge("collect_data", "run_cluster_sizing")
        workflow.add_edge("run_cluster_sizing", "validate_performance")
        workflow.add_edge("validate_performance", "assess_risks")
        workflow.add_edge("assess_risks", "generate_recommendation")
        workflow.add_conditional_edges(
            "generate_recommendation",
            route_after_recommendation,
            {"generate_explanation": "generate_explanation", "done": END},
        )
        workflow.add_edge("generate_explanation", END)
        return workflow.compile()

    async def run(self, job_id: str, start_date: str, end_date: str, **kwargs) -> Dict:
        return await self.generate_recommendation(
            job_id=job_id, start_date=start_date, end_date=end_date, **kwargs
        )

    async def generate_recommendation(
        self,
        job_id: str,
        start_date: str,
        end_date: str,
        job_run_id: Optional[str] = None,
        include_explanation: bool = False,
        job_run_ingest: Optional[Dict] = None,
        request_log_request_id: Optional[UUID] = None,
    ) -> Dict:
        logger.info("generating_recommendation", job_id=job_id, job_run_id=job_run_id)
        token_tracker = TokenUsageTracker()
        request_id = uuid4()
        initial_state: RecommendationState = {
            "job_id": job_id,
            "job_run_id": job_run_id or "",
            "start_date": start_date,
            "end_date": end_date,
            "include_explanation": include_explanation,
            "job_run_ingest_override": job_run_ingest,
            "job_cluster_metrics": {},
            "job_run_ingest": {},
            "sizing_hints": {},
            "resource_utilization": {},
            "cost_analysis": {},
            "pattern_analysis": "",
            "cost_optimization": {},
            "llm_recommendation": {},
            "guardrail_recommendation": {},
            "guardrail_adjustments": [],
            "recommendation_attempts": 0,
            "performance_validation": {},
            "risk_assessment": {},
            "recommendation": {},
            "explanation": "",
            "reason_codes": [],
            "token_tracker": token_tracker,
        }
        final_state = await self.graph.ainvoke(initial_state)
        token_usage_summary = token_tracker.get_summary()
        ingest = final_state.get("job_run_ingest") or {}
        recommendation = final_state.get("recommendation") or {}
        reason_codes = final_state.get("reason_codes") or []
        comparison_payload = build_recommendation_response_v2(
            recommendation_id=str(request_id),
            ingest=ingest,
            recommendation=recommendation,
            reason_codes=reason_codes,
            pattern_analysis=final_state.get("pattern_analysis", ""),
        )

        cost_logger = self.cost_logger
        model_name = self.settings.azure_openai_deployment_name or self.settings.default_model_name
        if cost_logger:
            try:
                for chain_name, chain_data in token_usage_summary["cost_estimate"][
                    "breakdown_by_chain"
                ].items():
                    cost_logger.log_token_usage(
                        request_id=request_id,
                        model_name=chain_data["model"],
                        chain_name=chain_name,
                        input_tokens=chain_data["input_tokens"],
                        output_tokens=chain_data["output_tokens"],
                        total_tokens=chain_data["input_tokens"] + chain_data["output_tokens"],
                        cost_usd=chain_data["total_cost_usd"],
                        job_id=job_id,
                    )
            except Exception as e:
                logger.warning("cost_logging_failed", error=str(e))
        if cost_logger:
            try:
                cost_logger.log_recommendation(
                    request_id=request_id,
                    job_id=job_id,
                    recommendation=recommendation,
                    explanation=final_state.get("explanation", ""),
                    pattern_analysis=final_state.get("pattern_analysis", ""),
                    risk_assessment=final_state.get("risk_assessment", {}),
                    token_usage_analysis=token_usage_summary,
                    request_log_request_id=request_log_request_id,
                    workspace_id=ingest.get("workspace_id"),
                    job_run_id=job_run_id or ingest.get("job_run_id"),
                    comparison=comparison_payload,
                    reason_codes=reason_codes,
                )
                try:
                    from shared.services.recommendation_lifecycle_service import (
                        RecommendationLifecycleService,
                    )

                    run_id = job_run_id or ingest.get("job_run_id")
                    if run_id:
                        RecommendationLifecycleService().supersede_prior_recommendations(
                            job_id=job_id,
                            job_run_id=str(run_id),
                            except_request_id=request_id,
                        )
                except Exception as e:
                    logger.warning("supersede_prior_recommendations_failed", error=str(e))
            except Exception as e:
                logger.warning("recommendation_logging_failed", error=str(e))

        search_service = self.search_service
        if search_service:
            try:
                recommendation_doc = {
                    "recommendation_id": str(request_id),
                    "job_id": job_id,
                    "job_run_id": job_run_id,
                    "workspace_id": ingest.get("workspace_id"),
                    "workload_type": ingest.get("workload_type", "Unknown"),
                    "rationale": recommendation.get("rationale", ""),
                    "detailed_explanation": final_state.get("explanation", ""),
                    **recommendation,
                }
                search_service.index_recommendation(recommendation_doc)
                search_service.link_recommendation_to_job(str(request_id), job_id)
            except Exception as e:
                logger.warning("recommendation_indexing_failed", error=str(e))

        current_configuration = comparison_payload["comparison"]["current_configuration"]
        return {
            "request_id": str(request_id),
            "job_run_id": job_run_id,
            "current_configuration": current_configuration,
            "recommendation": recommendation,
            "explanation": final_state.get("explanation", ""),
            "pattern_analysis": final_state.get("pattern_analysis", ""),
            "risk_assessment": final_state.get("risk_assessment", {}),
            "reason_codes": reason_codes,
            "job_run_ingest": ingest,
            "sizing_hints": final_state.get("sizing_hints", {}),
            "llm_recommendation": final_state.get("llm_recommendation", {}),
            "guardrail_recommendation": final_state.get("guardrail_recommendation", {}),
            "guardrail_adjustments": final_state.get("guardrail_adjustments", []),
            "recommendation_attempts": final_state.get("recommendation_attempts", 1),
            "comparison": comparison_payload,
            "token_usage_analysis": token_usage_summary,
        }


# Backward-compatible names
ClusterConfigAgent = JobRunClusterSizingAgent
