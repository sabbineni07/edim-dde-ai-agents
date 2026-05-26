"""Format retrieval hits into prompt strings (shared by Azure and FAISS providers)."""

from typing import Any, Dict, List


def format_recommendation_hits_for_cost_chain(recommendations: List[Dict[str, Any]]) -> str:
    """Build historical_context from similar recommendation documents."""
    if not recommendations:
        return ""
    rec_contexts = []
    for rec in recommendations[:3]:
        rec_data = rec.get("recommendation", {})
        if not isinstance(rec_data, dict):
            rec_data = {}
        rec_contexts.append(
            f"- Recommended: {rec_data.get('node_family', 'N/A')} family, "
            f"{rec_data.get('vcpus', 'N/A')} vCPUs, "
            f"{rec_data.get('min_workers', 'N/A')}-{rec_data.get('max_workers', 'N/A')} workers. "
            f"Rationale: {str(rec_data.get('rationale', 'N/A'))[:100]}"
        )
    return f"""

Similar Successful Recommendations Found ({len(recommendations)}):
{chr(10).join(rec_contexts)}

Use these as guidance, but optimize based on current job's actual needs.
"""


def format_job_pattern_hits_for_cost_chain(jobs: List[Dict[str, Any]]) -> str:
    """Build historical_context from job_cluster_metrics-style hits (utilization only)."""
    if not jobs:
        return ""
    patterns = []
    for job in jobs:
        metrics = job.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        patterns.append(
            {
                "cpu": metrics.get("avg_cpu_utilization_pct", 0),
                "memory": metrics.get("avg_memory_utilization_pct", 0),
                "nodes": metrics.get("avg_nodes_consumed", 0),
            }
        )
    if not patterns:
        return ""
    avg_cpu = sum(p["cpu"] for p in patterns) / len(patterns)
    avg_memory = sum(p["memory"] for p in patterns) / len(patterns)
    avg_nodes = sum(p["nodes"] for p in patterns) / len(patterns)
    return f"""

Similar Workload Patterns Found ({len(patterns)} jobs):
- Average CPU: {avg_cpu:.1f}%
- Average Memory: {avg_memory:.1f}%
- Average Nodes: {avg_nodes:.1f}

NOTE: These are utilization patterns for context only.
Historical configurations may be suboptimal. Optimize based on
utilization needs, not by copying historical configs.
"""


def format_job_patterns_for_pattern_chain(jobs: List[Dict[str, Any]]) -> str:
    """Build historical_context for pattern analysis from similar jobs."""
    if not jobs:
        return ""
    patterns = []
    for job in jobs:
        metrics = job.get("metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        patterns.append(
            {
                "cpu": metrics.get("avg_cpu_utilization_pct", 0),
                "memory": metrics.get("avg_memory_utilization_pct", 0),
                "nodes": metrics.get("avg_nodes_consumed", 0),
                "workload_type": job.get("workload_type", "Unknown"),
            }
        )
    if not patterns:
        return ""
    avg_cpu = sum(p["cpu"] for p in patterns) / len(patterns)
    avg_memory = sum(p["memory"] for p in patterns) / len(patterns)
    avg_nodes = sum(p["nodes"] for p in patterns) / len(patterns)
    workload_types = [p["workload_type"] for p in patterns]
    most_common_workload = max(set(workload_types), key=workload_types.count)
    return f"""

Similar Historical Workload Patterns Found ({len(patterns)} jobs):
- Most common workload type: {most_common_workload}
- Average CPU utilization: {avg_cpu:.1f}%
- Average Memory utilization: {avg_memory:.1f}%
- Average nodes consumed: {avg_nodes:.1f}

IMPORTANT: These are utilization patterns from similar jobs for context.
Historical configurations may be suboptimal. Focus on analyzing the
utilization patterns to understand workload needs, not copying historical configs.
"""
