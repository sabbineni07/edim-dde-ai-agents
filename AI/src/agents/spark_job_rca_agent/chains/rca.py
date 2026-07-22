"""RCA synthesis chain — single LLM call over an evidence pack."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from AI.src.core.llm.chat_model_factory import resolve_chain_llm
from AI.src.core.prompts.loader import build_chain_messages
from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.rca.prompt_payload import format_rca_human_payload
from shared.utils.logging import get_logger

if TYPE_CHECKING:
    from shared.abstractions.protocols import LLMProvider

logger = get_logger(__name__)


def _extract_json_from_response(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    text = text.strip()
    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_block:
        return code_block.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text


class RcaSynthesisChain:
    """Produce grounded RCA JSON from evidence_pack + classification hint."""

    def __init__(
        self,
        llm_provider: Optional["LLMProvider"] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings: Settings = settings or default_settings
        self.llm = resolve_chain_llm(self.settings, chain="rca", llm_provider=llm_provider)
        self.prompt = ChatPromptTemplate.from_messages(
            build_chain_messages(SPARK_JOB_RCA_AGENT_ID, "rca", settings=self.settings)
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    def invoke(
        self,
        *,
        evidence_pack: Dict[str, Any],
        classification_hint: str,
        token_tracker: Any = None,
    ) -> Dict[str, Any]:
        payload = format_rca_human_payload(
            evidence_pack,
            classification_hint=classification_hint,
        )
        text = ""
        try:
            text = self.chain.invoke(payload) or ""
        except Exception as e:
            logger.warning("rca_llm_invoke_failed", error=str(e))
            return {}

        if token_tracker is not None and hasattr(token_tracker, "estimate_chain_usage"):
            model = getattr(self.settings, "azure_openai_deployment_name", None) or "gpt-4o"
            token_tracker.estimate_chain_usage("rca", model, payload, text)

        raw_json = _extract_json_from_response(text)
        if not raw_json:
            logger.warning("rca_llm_empty_or_unparseable")
            return {}
        try:
            parsed = json.loads(raw_json)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as e:
            logger.warning("rca_llm_json_parse_failed", error=str(e))
            return {}
