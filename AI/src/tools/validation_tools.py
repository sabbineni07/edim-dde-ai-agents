"""Validation tools for LangChain."""

import re
from typing import Dict

from langchain_core.tools import tool


def parse_vcpus_from_node_type(node_type: str) -> int:
    """Parse vCPUs from Azure VM node type.

    Azure VM naming convention: Standard_{Family}{Number}s_v{Version}
    Examples:
        Standard_E8s_v3 -> 8 vCPUs
        Standard_D4s_v3 -> 4 vCPUs
        Standard_E16s_v3 -> 16 vCPUs
        Standard_F8s_v2 -> 8 vCPUs

    Args:
        node_type: Azure VM node type (e.g., "Standard_E8s_v3")

    Returns:
        Number of vCPUs, or 8 as default if parsing fails
    """
    if not node_type:
        return 8  # Default fallback

    # Pattern: Standard_{Family}{Number}s_v{Version} (Family: D, E, F, L)
    # Extract the number after the family letter and before 's'
    match = re.search(r"Standard_[DEFL]\d+", node_type)
    if match:
        # Extract the number part (e.g., "E8" -> "8")
        number_match = re.search(r"\d+", match.group())
        if number_match:
            return int(number_match.group())

    # Fallback to default if parsing fails
    return 8


@tool
def validate_performance(
    current_peak_cpu: float,
    current_peak_memory: float,
    recommended_vcpus: int,
    recommended_max_workers: int,
    current_vcpus: int,
    current_max_workers: int,
) -> Dict:
    """Validate that recommended configuration meets performance requirements.

    Args:
        current_peak_cpu: Current peak CPU utilization percentage
        current_peak_memory: Current peak memory utilization percentage
        recommended_vcpus: Recommended vCPUs per node
        recommended_max_workers: Recommended max workers
        current_vcpus: Current vCPUs per node
        current_max_workers: Current max workers

    Returns:
        Dictionary with validation results
    """
    current_capacity = current_vcpus * current_max_workers
    recommended_capacity = recommended_vcpus * recommended_max_workers

    # Conservative check: recommended should be at least 80% of current
    meets_requirements = recommended_capacity >= (current_capacity * 0.8)

    # Check if we're reducing too much
    reduction_pct = (
        ((current_capacity - recommended_capacity) / current_capacity * 100)
        if current_capacity > 0
        else 0
    )
    risk_level = "HIGH" if reduction_pct > 20 else "MEDIUM" if reduction_pct > 10 else "LOW"

    return {
        "meets_peak_requirements": meets_requirements,
        "current_capacity": current_capacity,
        "recommended_capacity": recommended_capacity,
        "reduction_pct": reduction_pct,
        "risk_level": risk_level,
        "estimated_impact": "MAINTAINED" if meets_requirements else "DEGRADATION_RISK",
    }


@tool
def assess_risks(
    configuration_change_magnitude: float, performance_validation: Dict, cost_savings_pct: float
) -> Dict:
    """Assess risks of recommendation.

    Args:
        configuration_change_magnitude: Percentage change in configuration
        performance_validation: Results from validate_performance
        cost_savings_pct: Percentage of cost savings

    Returns:
        Dictionary with risk assessment
    """
    risk_score = 0.0

    # Configuration change risk
    if configuration_change_magnitude > 50:
        risk_score += 0.4
    elif configuration_change_magnitude > 25:
        risk_score += 0.2

    # Performance risk
    if not performance_validation.get("meets_peak_requirements", True):
        risk_score += 0.3

    if performance_validation.get("risk_level") == "HIGH":
        risk_score += 0.2

    # Cost risk (aggressive savings might indicate risk)
    if cost_savings_pct > 40:
        risk_score += 0.1

    # Determine risk level
    if risk_score >= 0.6:
        risk_level = "HIGH"
    elif risk_score >= 0.3:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    mitigations = []
    if risk_level == "HIGH":
        mitigations.append("Monitor initial runs closely")
        mitigations.append("Maintain rollback capability")
        mitigations.append("Gradual rollout recommended")
    elif risk_level == "MEDIUM":
        mitigations.append("Monitor first few runs")
        mitigations.append("Maintain previous configuration")

    return {"risk_level": risk_level, "risk_score": risk_score, "mitigations": mitigations}
