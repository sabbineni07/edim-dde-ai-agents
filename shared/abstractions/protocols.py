"""Protocol definitions for service abstractions."""

from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID


class BaseAgent(Protocol):
    """Protocol for agents. All agents must have agent_id and a run method."""

    agent_id: str

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Run the agent. Input/output shape is agent-specific."""
        ...


class LLMProvider(Protocol):
    """Protocol for LLM/embeddings providers (e.g. Azure OpenAI)."""

    def get_llm(self):
        """Return the LLM instance for chat completions."""
        ...

    def get_embeddings(self):
        """Return the embeddings model, or None if not available."""
        ...


class SearchService(Protocol):
    """Protocol for vector/search services (e.g. Azure AI Search)."""

    def search_similar(self, query: str, top_k: int = 5, filter_quality: bool = True) -> List[Dict]:
        """Search for similar recommendations."""
        ...

    def search_similar_jobs(
        self,
        job_cluster_metrics: dict,
        top_k: int = 5,
        filter_recommendations: bool = False,
    ) -> List[Dict]:
        """Search for similar job patterns."""
        ...

    def index_recommendation(self, recommendation: dict) -> bool:
        """Index a recommendation. Returns False if search not available."""
        ...

    def link_recommendation_to_job(self, recommendation_id: str, job_id: str) -> bool:
        """Link recommendation to job. Returns False if search not available."""
        ...


class DataCollector(Protocol):
    """Protocol for data collectors (local CSV, Databricks, etc.)."""

    def collect_job_cluster_metrics(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
    ) -> List[Any]:
        """Collect job cluster metrics."""
        ...

    def collect_cost_data(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Collect cost data."""
        ...


class CostLogger(Protocol):
    """Protocol for cost and recommendation logging."""

    def log_token_usage(
        self,
        request_id: UUID,
        model_name: str,
        chain_name: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cost_usd: float,
        job_id: Optional[str] = None,
        user_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> bool:
        """Log token usage and cost."""
        ...

    def log_recommendation(
        self,
        request_id: UUID,
        job_id: str,
        recommendation: dict,
        explanation: str,
        pattern_analysis: str,
        risk_assessment: dict,
        token_usage_analysis: Optional[dict] = None,
    ) -> bool:
        """Log recommendation to history."""
        ...
