"""Cost calculation tools for LangChain."""

from typing import Dict

from langchain_core.tools import tool

# Node type pricing (example - should come from actual pricing data or API)
NODE_PRICING = {
    "Standard_D4s_v3": 0.192,  # per hour
    "Standard_D8s_v3": 0.384,
    "Standard_E8s_v3": 0.384,
    "Standard_E16s_v3": 0.768,
    "Standard_F8s_v2": 0.336,
    "Standard_F16s_v2": 0.672,
}


@tool
def calculate_cluster_cost(
    node_type: str, min_workers: int, max_workers: int, avg_nodes: float, hours_per_month: float
) -> Dict:
    """Calculate monthly cluster cost.

    Args:
        node_type: Node type (e.g., Standard_E8s_v3)
        min_workers: Minimum number of workers
        max_workers: Maximum number of workers
        avg_nodes: Average number of nodes consumed
        hours_per_month: Hours of usage per month

    Returns:
        Dictionary with cost breakdown
    """
    hourly_rate = NODE_PRICING.get(node_type, 0.2)
    monthly_cost = hourly_rate * avg_nodes * hours_per_month

    return {
        "node_type": node_type,
        "hourly_rate": hourly_rate,
        "avg_nodes": avg_nodes,
        "hours_per_month": hours_per_month,
        "monthly_cost": monthly_cost,
    }


@tool
def calculate_cost_savings(current_cost: float, recommended_cost: float) -> Dict:
    """Calculate cost savings from recommendation.

    Args:
        current_cost: Current monthly cost
        recommended_cost: Recommended monthly cost

    Returns:
        Dictionary with savings breakdown
    """
    savings_usd = current_cost - recommended_cost
    savings_pct = (savings_usd / current_cost * 100) if current_cost > 0 else 0

    return {
        "current_cost": current_cost,
        "recommended_cost": recommended_cost,
        "savings_usd": savings_usd,
        "savings_pct": savings_pct,
        "annual_savings": savings_usd * 12,
    }
