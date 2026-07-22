"""Dependency wiring for the Spark job RCA agent."""

from typing import Any, Dict, Optional

from AI.src.agents.spark_job_rca_agent.chains.rca import RcaSynthesisChain
from AI.src.core.platform import get_cost_logger
from shared.config.agent_ids import SPARK_JOB_RCA_AGENT_ID
from shared.config.loader import get_agent_settings
from shared.config.settings import Settings

AGENT_ID = SPARK_JOB_RCA_AGENT_ID


def get_rca_chain(
    llm_provider=None,
    settings: Optional[Settings] = None,
    agent_id: str = AGENT_ID,
) -> RcaSynthesisChain:
    agent_settings = settings or get_agent_settings(agent_id)
    return RcaSynthesisChain(llm_provider=llm_provider, settings=agent_settings)


def build_agent_runtime_deps(
    settings: Settings,
    agent_id: str = AGENT_ID,
) -> Dict[str, Any]:
    return {
        "rca_chain": get_rca_chain(agent_id=agent_id, settings=settings),
    }


def get_spark_job_rca_agent_deps(agent_id: str = AGENT_ID) -> dict:
    agent_settings = get_agent_settings(agent_id)
    return {
        **build_agent_runtime_deps(agent_settings, agent_id=agent_id),
        "cost_logger": get_cost_logger(),
        "settings": agent_settings,
    }
