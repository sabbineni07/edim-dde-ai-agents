"""Explanation generation chain."""

from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from AI.src.core.llm.chat_model_factory import can_create_chat_model, create_chat_model
from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import LLMProvider

logger = get_logger(__name__)


class RecommendationExplanationChain:
    """LangChain for generating detailed explanations."""

    def __init__(
        self,
        llm_provider: Optional["LLMProvider"] = None,
        settings: Optional[Settings] = None,
    ):
        """Initialize explanation chain.

        Args:
            llm_provider: LLM provider fallback when settings lack a Foundry endpoint
            settings: Effective agent settings (workspace overrides + YAML)
        """
        self.settings: Settings = settings or default_settings
        if can_create_chat_model(self.settings):
            self.llm = create_chat_model(self.settings, chain="explanation")
        else:
            from AI.src.core.platform import get_llm_provider

            provider = llm_provider or get_llm_provider()
            self.llm = provider.get_llm("explanation")

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """## Role
You are an expert at explaining Databricks cluster sizing recommendations. Your explanation helps platform and data engineers decide whether to apply the recommendation.

## Task
Using only the inputs below, produce a structured explanation that: justifies the recommendation with evidence from the job run, compares current vs recommended configuration, states expected impact and risks, and briefly notes alternatives. Ground every claim in the inputs; avoid generic filler.

## Inputs you will receive
- **Recommendation:** The proposed cluster configuration (node_family, vcpus, min_workers, max_workers, auto_termination_minutes, rationale). This is what you are explaining.
- **Job run ingest:** Observed utilization and configuration for this run (worker/driver CPU and memory %, nodes consumed, VM sizes, provisioned ceiling). Quote specific numbers in Rationale and Evidence.
- **Pattern analysis:** Prior workload and utilization analysis from the sizing step.
- **Risk assessment:** Risk level and mitigations from validation.

## Priorities
- Be specific: cite numbers from job run ingest and pattern analysis.
- Keep sections focused and short; use bullets where appropriate.

## Output structure
Use exactly these markdown headings. One short block per section.
### 1. Rationale
### 2. Evidence
### 3. Current vs recommended configuration
### 4. Expected impact
### 5. Risks and mitigations
### 6. Alternatives""",
                ),
                (
                    "human",
                    """## Input: Recommendation
{recommendation}

## Input: Job run ingest
{job_run_ingest}

## Input: Pattern analysis
{pattern_analysis}

## Input: Risk assessment
{risk_assessment}

## Instruction
Using only the four inputs above, write the structured explanation with the six sections. Cite specific numbers from job run ingest where they support the recommendation.""",
                ),
            ]
        )

        self.chain = self.prompt | self.llm | StrOutputParser()

    def explain(
        self,
        recommendation: dict,
        job_run_ingest: dict,
        pattern_analysis: str,
        risk_assessment: dict,
    ) -> str:
        """Generate detailed explanation."""
        try:
            from shared.models.job_run_ingest import format_job_run_ingest_for_llm

            result = self.chain.invoke(
                {
                    "recommendation": format_job_run_ingest_for_llm(recommendation),
                    "job_run_ingest": format_job_run_ingest_for_llm(job_run_ingest),
                    "pattern_analysis": pattern_analysis,
                    "risk_assessment": format_job_run_ingest_for_llm(risk_assessment),
                }
            )
            logger.info("explanation_generated")
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error("explanation_error", error=str(e))
            raise
