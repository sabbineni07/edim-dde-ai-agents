"""Explanation generation chain."""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from AI.src.services.azure_openai_service import AzureOpenAIService
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class ExplanationChain:
    """LangChain for generating detailed explanations."""
    
    def __init__(self):
        """Initialize explanation chain."""
        self.llm = AzureOpenAIService().get_llm()
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """## Role
You are an expert at explaining Databricks cluster recommendations. Your explanation will be read by platform or data engineers to decide whether to apply the recommendation.

## Task
Using only the inputs provided below, produce a structured explanation that: justifies the recommendation with metrics, compares current vs recommended configuration, states expected impact and risks, and briefly notes alternatives. Every claim should be grounded in the inputs; avoid generic filler.

## Inputs you will receive
- **Recommendation:** The chosen configuration (node_family, vcpus, min_workers, max_workers, auto_termination_minutes, rationale) and any cost/savings fields. This is what you are explaining.
- **Job cluster metrics:** The metrics used to produce the recommendation (e.g. avg/peak CPU and memory, avg_nodes_consumed, p95, current_node_type, current_max_workers). Quote these when explaining rationale and evidence.
- **Pattern analysis:** Previous analysis of workload type and utilization. Use it to support your rationale and evidence.
- **Risk assessment:** Risk level and mitigations from a prior step. Use it to populate the Risks and mitigations section; you may add more risks or mitigations if needed.

## Priorities
- Be specific: cite numbers from job cluster metrics and pattern analysis in Rationale and Evidence.
- Keep sections focused and short; use bullets for lists where appropriate.

## Output structure
Use exactly these markdown headings. One short block per section.
### 1. Rationale
### 2. Evidence
### 3. Current vs recommended configuration
### 4. Expected impact
### 5. Risks and mitigations
### 6. Alternatives"""),
            ("human", """## Input: Recommendation
{recommendation}

## Input: Job cluster metrics
{job_cluster_metrics}

## Input: Pattern analysis
{pattern_analysis}

## Input: Risk assessment
{risk_assessment}

## Instruction
Using only the four inputs above, write the structured explanation with the six sections: Rationale, Evidence, Current vs recommended configuration, Expected impact, Risks and mitigations, Alternatives. Cite specific numbers from the inputs.""")
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()
    
    def explain(
        self,
        recommendation: dict,
        job_cluster_metrics: dict,
        pattern_analysis: str,
        risk_assessment: dict
    ) -> str:
        """Generate detailed explanation."""
        try:
            result = self.chain.invoke({
                "recommendation": str(recommendation),
                "job_cluster_metrics": str(job_cluster_metrics),
                "pattern_analysis": pattern_analysis,
                "risk_assessment": str(risk_assessment)
            })
            logger.info("explanation_generated")
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error("explanation_error", error=str(e))
            raise

