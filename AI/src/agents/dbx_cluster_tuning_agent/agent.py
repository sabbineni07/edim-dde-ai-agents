"""DBX cluster tuning agent — per job-run Databricks cluster utilization right-sizing."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph

from AI.src.agents.dbx_cluster_tuning_agent.chains.explanation import RecommendationExplanationChain
from AI.src.agents.dbx_cluster_tuning_agent.chains.sizing import (
    SIZING_RECOMMENDATION_KEYS,
    ClusterSizingChain,
    split_sizing_llm_response,
)
from AI.src.agents.dbx_cluster_tuning_agent.tools.cost_calculator_tools import (
    calculate_cluster_cost,
    calculate_cost_savings,
)
from AI.src.agents.dbx_cluster_tuning_agent.tools.databricks_tools import (
    get_cost_analysis,
    get_job_cluster_metrics,
)
from AI.src.agents.dbx_cluster_tuning_agent.tools.validation_tools import (
    assess_risks,
    parse_vcpus_from_node_type,
    validate_performance,
)
from AI.src.core.registry import register_agent
from AI.src.core.utils.token_usage import TokenUsageTracker
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
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

AGENT_ID = DBX_CLUSTER_TUNING_AGENT_ID


class RecommendationState(TypedDict, total=False):
    job_id: str
    cluster_id: str
    job_run_id: str
    start_date: Optional[str]
    end_date: Optional[str]
    include_explanation: bool
    job_cluster_metrics_override: Optional[Dict]
    job_cluster_metrics: Dict
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


def _register_dbx_cluster_tuning_agent(cls):
    from AI.src.agents.dbx_cluster_tuning_agent.deps import get_dbx_cluster_tuning_agent_deps

    return register_agent(
        AGENT_ID,
        deps_factory=get_dbx_cluster_tuning_agent_deps,
    )(cls)


@_register_dbx_cluster_tuning_agent
class DbxClusterTuningAgent:
    """Recommend cluster right-sizing for a single Databricks job run."""

    agent_id = AGENT_ID

    def __init__(
        self,
        sizing_chain: ClusterSizingChain,
        explanation_chain: RecommendationExplanationChain,
        settings: Optional[Settings] = None,
        cost_logger: Optional["CostLogger"] = None,
        search_service: Optional["SearchService"] = None,
    ):
        if sizing_chain is None:
            raise TypeError("sizing_chain is required")
        self.sizing_chain = sizing_chain
        self.explanation_chain = explanation_chain
        self.cost_logger = cost_logger
        self.search_service = search_service
        self.settings: Settings = settings or get_agent_settings(AGENT_ID)
        self.graph = self._create_recommendation_graph()
        logger.info("dbx_cluster_tuning_agent_initialized")

    def _metrics_from_state(self, state: RecommendationState) -> Dict:
        return state.get("job_cluster_metrics") or {}

    def _create_recommendation_graph(self) -> StateGraph:
        sizing_chain = self.sizing_chain
        explanation_chain = self.explanation_chain
        model_name = self.settings.azure_openai_deployment_name or self.settings.default_model_name

        def collect_data(state: RecommendationState) -> RecommendationState:
            cluster_id = state.get("cluster_id") or state.get("job_run_id")
            logger.info(
                "collecting_job_data",
                job_id=state["job_id"],
                cluster_id=cluster_id,
            )
            override = state.get("job_cluster_metrics_override")
            if override:
                state["job_cluster_metrics"] = to_llm_ingest_dict(override)
            else:
                state["job_cluster_metrics"] = get_job_cluster_metrics.invoke(
                    {
                        "job_id": state["job_id"],
                        "cluster_id": cluster_id,
                        "start_date": state.get("start_date") or None,
                        "end_date": state.get("end_date") or None,
                    }
                )
            metrics = state["job_cluster_metrics"]
            if not metrics or not isinstance(metrics, dict) or len(metrics) == 0:
                raise NoJobMetricsError(
                    job_id=state["job_id"],
                    start_date=state.get("start_date") or "",
                    end_date=state.get("end_date") or "",
                    job_run_id=cluster_id,
                )
            run_date = str(metrics.get("job_run_date") or "").strip()
            policy = default_sizing_policy()
            state["sizing_hints"] = compute_sizing_hints(metrics, policy)
            state["resource_utilization"] = {
                "peak_worker_cpu_utilization_pct": metrics.get(
                    "peak_worker_cpu_utilization_pct", 0
                ),
                "peak_worker_memory_utilization_pct": metrics.get(
                    "peak_worker_memory_utilization_pct", 0
                ),
                "avg_worker_nodes_consumed": metrics.get("avg_worker_nodes_consumed", 0),
            }
            cost_start = state.get("start_date") or run_date
            cost_end = state.get("end_date") or run_date
            state["cost_analysis"] = get_cost_analysis.invoke(
                {
                    "job_id": state["job_id"],
                    "start_date": cost_start,
                    "end_date": cost_end,
                }
            )
            return state

        def run_cluster_sizing(state: RecommendationState) -> RecommendationState:
            metrics = self._metrics_from_state(state)
            hints = state.get("sizing_hints") or compute_sizing_hints(metrics)
            narrow_hints = sizing_hints_for_llm(hints)
            current_config = {
                "azure_worker_vm_size": metrics.get("azure_worker_vm_size", "Standard_E8s_v3"),
                "driver_node_count": metrics.get("driver_node_count", 1),
                "max_worker_nodes_provisioned": metrics.get("max_worker_nodes_provisioned", 16),
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
                    metrics,
                    narrow_hints,
                    guardrail_feedback=feedback,
                )
                pattern_text, llm_rec = split_sizing_llm_response(llm_sizing)
                state["pattern_analysis"] = pattern_text
                applied, adjustments = validate_and_clamp_with_adjustments(
                    llm_rec, job_run_ingest=metrics
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
                        "job_cluster_metrics": metrics,
                        "sizing_hints": narrow_hints,
                        "recommendation_attempts": attempts,
                    },
                    output_text=llm_sizing,
                )
            return state

        def validate_performance_node(state: RecommendationState) -> RecommendationState:
            metrics = self._metrics_from_state(state)
            ru = state["resource_utilization"]
            current_node_type = metrics.get("azure_worker_vm_size", "Standard_E8s_v3")
            current_vcpus = parse_vcpus_from_node_type(current_node_type)
            current_max_workers = int(metrics.get("max_worker_nodes_provisioned", 16))
            recommended_vcpus = state["cost_optimization"].get("vcpus", 8)
            recommended_max_workers = state["cost_optimization"].get("max_workers", 8)
            state["performance_validation"] = validate_performance.invoke(
                {
                    "current_peak_cpu": ru.get("peak_worker_cpu_utilization_pct", 0),
                    "current_peak_memory": ru.get("peak_worker_memory_utilization_pct", 0),
                    "recommended_vcpus": recommended_vcpus,
                    "recommended_max_workers": recommended_max_workers,
                    "current_vcpus": current_vcpus,
                    "current_max_workers": current_max_workers,
                    "job_run_ingest": metrics,
                }
            )
            return state

        def assess_risks_node(state: RecommendationState) -> RecommendationState:
            metrics = self._metrics_from_state(state)
            current_vcpus = parse_vcpus_from_node_type(
                metrics.get("azure_worker_vm_size", "Standard_E8s_v3")
            )
            current_max = int(metrics.get("max_worker_nodes_provisioned", 16))
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
            metrics = self._metrics_from_state(state)
            current_node_type = metrics.get("azure_worker_vm_size", "Standard_E8s_v3")
            co = state["cost_optimization"]
            recommended_node_type = co.get("azure_node_type") or nearest_allowed_node_type(
                co.get("node_family", "E"),
                co.get("vcpus", 8),
                current_node_type=current_node_type,
            )
            avg_nodes = float(metrics.get("avg_worker_nodes_consumed") or 4)
            current_cost = calculate_cluster_cost.invoke(
                {
                    "node_type": current_node_type,
                    "min_workers": max(int(metrics.get("driver_node_count", 1)) - 1, 0),
                    "max_workers": int(metrics.get("max_worker_nodes_provisioned", 16)),
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
            ) != int(metrics.get("max_worker_nodes_provisioned", 16))
            state["reason_codes"] = infer_reason_codes(
                metrics, state["recommendation"], change_required=change_required
            )
            return state

        def generate_explanation_node(state: RecommendationState) -> RecommendationState:
            metrics = self._metrics_from_state(state)
            result = explanation_chain.explain(
                recommendation=state["recommendation"],
                job_run_ingest=metrics,
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

    async def run(self, job_id: str, cluster_id: str, **kwargs) -> Dict:
        return await self.generate_recommendation(job_id=job_id, cluster_id=cluster_id, **kwargs)

    async def generate_recommendation(
        self,
        job_id: str,
        cluster_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        include_explanation: bool = False,
        job_cluster_metrics: Optional[Dict] = None,
        job_run_id: Optional[str] = None,
        job_run_ingest: Optional[Dict] = None,
        request_log_request_id: Optional[UUID] = None,
    ) -> Dict:
        run_id = (cluster_id or job_run_id or "").strip()
        metrics_override = job_cluster_metrics or job_run_ingest
        logger.info("generating_recommendation", job_id=job_id, cluster_id=run_id)
        token_tracker = TokenUsageTracker()
        request_id = uuid4()
        initial_state: RecommendationState = {
            "job_id": job_id,
            "cluster_id": run_id,
            "job_run_id": run_id,
            "start_date": start_date,
            "end_date": end_date,
            "include_explanation": include_explanation,
            "job_cluster_metrics_override": metrics_override,
            "job_cluster_metrics": {},
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
        metrics = final_state.get("job_cluster_metrics") or {}
        recommendation = final_state.get("recommendation") or {}
        reason_codes = final_state.get("reason_codes") or []
        comparison_payload = build_recommendation_response_v2(
            recommendation_id=str(request_id),
            ingest=metrics,
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
                    workspace_id=metrics.get("workspace_id"),
                    job_run_id=run_id or metrics.get("cluster_id"),
                    comparison=comparison_payload,
                    reason_codes=reason_codes,
                )
                try:
                    from shared.services.recommendation_lifecycle_service import (
                        RecommendationLifecycleService,
                    )

                    run_id = run_id or metrics.get("cluster_id")
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
                    "cluster_id": run_id,
                    "job_run_id": run_id,
                    "workspace_id": metrics.get("workspace_id"),
                    "job_type": metrics.get("job_type", "Unknown"),
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
            "cluster_id": run_id,
            "job_run_id": run_id,
            "current_configuration": current_configuration,
            "recommendation": recommendation,
            "explanation": final_state.get("explanation", ""),
            "pattern_analysis": final_state.get("pattern_analysis", ""),
            "risk_assessment": final_state.get("risk_assessment", {}),
            "reason_codes": reason_codes,
            "job_cluster_metrics": metrics,
            "job_run_ingest": metrics,
            "sizing_hints": final_state.get("sizing_hints", {}),
            "llm_recommendation": final_state.get("llm_recommendation", {}),
            "guardrail_recommendation": final_state.get("guardrail_recommendation", {}),
            "guardrail_adjustments": final_state.get("guardrail_adjustments", []),
            "recommendation_attempts": final_state.get("recommendation_attempts", 1),
            "comparison": comparison_payload,
            "token_usage_analysis": token_usage_summary,
        }
