"""Explanation generation chain."""

from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from AI.src.core.llm.chat_model_factory import can_create_chat_model, create_chat_model
from AI.src.core.prompts.loader import build_chain_messages
from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID
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
            build_chain_messages(DBX_CLUSTER_TUNING_AGENT_ID, "explanation", settings=self.settings)
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
