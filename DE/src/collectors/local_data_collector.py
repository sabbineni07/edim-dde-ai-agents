"""Local CSV data collector for testing and development."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)


class LocalDataCollector:
    """Collects data from local CSV files for local development and testing."""

    def __init__(self, csv_path: Optional[str] = None):
        """Initialize the local data collector.

        Args:
            csv_path: Path to the CSV file. Defaults to data/sample_job_metrics.csv
        """
        if csv_path is None:
            # Default to sample data in the project root
            project_root = Path(__file__).parent.parent.parent.parent
            csv_path = project_root / "data" / "sample_job_metrics.csv"

        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        logger.info("local_data_collector_initialized", csv_path=str(self.csv_path))

    def collect_job_cluster_metrics(
        self,
        start_date: str,
        end_date: str,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Collect job cluster metrics from CSV file.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            job_ids: Optional list of job IDs to filter
            workspace_id: Optional workspace ID to filter

        Returns:
            List of JobClusterMetrics objects
        """
        logger.info(
            "collecting_job_cluster_metrics_from_csv",
            start_date=start_date,
            end_date=end_date,
            job_count=len(job_ids) if job_ids else None,
            csv_path=str(self.csv_path),
        )

        try:
            # Read CSV file
            df = pd.read_csv(self.csv_path)
            logger.info("local_csv_loaded", rows=len(df), path=str(self.csv_path))

            # Normalize job_id and workspace_id to string for filtering (CSV may have numeric types)
            if "job_id" in df.columns:
                df["job_id"] = df["job_id"].astype(str)
            if "workspace_id" in df.columns:
                df["workspace_id"] = df["workspace_id"].astype(str)

            # Convert date column to datetime for filtering
            df["date"] = pd.to_datetime(df["date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)

            # Filter by date range (end_date is exclusive)
            df_filtered = df[(df["date"] >= start_dt) & (df["date"] < end_dt)]
            logger.info(
                "local_csv_after_date_filter", rows=len(df_filtered), start=start_date, end=end_date
            )

            # Filter by job_ids if provided
            if job_ids:
                job_ids_str = [str(j) for j in job_ids]
                df_filtered = df_filtered[df_filtered["job_id"].isin(job_ids_str)]
                logger.info(
                    "local_csv_after_job_id_filter", rows=len(df_filtered), job_ids=job_ids_str
                )

            # Filter by workspace_id if provided
            if workspace_id:
                df_filtered = df_filtered[df_filtered["workspace_id"] == str(workspace_id)]

            # Convert date back to string format
            df_filtered = df_filtered.copy()
            df_filtered["date"] = df_filtered["date"].dt.strftime("%Y-%m-%d")

            # Convert to JobClusterMetrics objects
            metrics = []
            for _, row in df_filtered.iterrows():
                try:
                    # Convert row to dict and handle NaN values
                    row_dict = row.to_dict()
                    # Replace NaN with None for optional fields and ensure string types
                    for key, value in row_dict.items():
                        if pd.isna(value):
                            row_dict[key] = None
                        # Ensure workspace_id and job_id are strings
                        elif key in ["workspace_id", "job_id", "job_run_id"] and value is not None:
                            row_dict[key] = str(value)

                    metric = JobClusterMetrics(**row_dict)
                    metrics.append(metric)
                except Exception as e:
                    logger.warning("failed_to_parse_metric", error=str(e), row=row.to_dict())

            # Log first record summary for validation
            if metrics:
                first = metrics[0]
                rec = first.model_dump() if hasattr(first, "model_dump") else first.dict()
                logger.info(
                    "collected_job_cluster_metrics_from_csv",
                    count=len(metrics),
                    first_record_job_id=rec.get("job_id"),
                    first_record_date=rec.get("date"),
                    first_record_keys=list(rec.keys())[:15],
                )
            else:
                logger.warning(
                    "collected_job_cluster_metrics_from_csv",
                    count=0,
                    message="no_records_after_filter",
                )
            return metrics

        except Exception as e:
            logger.error("local_collection_error", error=str(e))
            raise

    def collect_resource_utilization(
        self, start_date: str, end_date: str, job_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """Collect resource utilization metrics from CSV.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            job_ids: Optional list of job IDs to filter

        Returns:
            List of dictionaries containing resource utilization metrics
        """
        logger.info(
            "collecting_resource_utilization_from_csv", start_date=start_date, end_date=end_date
        )

        try:
            # Get job metrics first
            metrics = self.collect_job_cluster_metrics(start_date, end_date, job_ids)

            if not metrics:
                return []

            # Aggregate resource utilization by job_id
            utilization_by_job = {}
            for metric in metrics:
                job_id = metric.job_id
                if job_id not in utilization_by_job:
                    utilization_by_job[job_id] = {
                        "job_id": job_id,
                        "avg_cpu_utilization_pct": [],
                        "avg_memory_utilization_pct": [],
                        "peak_cpu_utilization_pct": [],
                        "peak_memory_utilization_pct": [],
                        "avg_nodes_consumed": [],
                        "p95_nodes_consumed": [],
                        "p99_nodes_consumed": [],
                    }

                utilization_by_job[job_id]["avg_cpu_utilization_pct"].append(
                    metric.avg_cpu_utilization_pct
                )
                utilization_by_job[job_id]["avg_memory_utilization_pct"].append(
                    metric.avg_memory_utilization_pct
                )
                utilization_by_job[job_id]["peak_cpu_utilization_pct"].append(
                    metric.peak_cpu_utilization_pct
                )
                utilization_by_job[job_id]["peak_memory_utilization_pct"].append(
                    metric.peak_memory_utilization_pct
                )
                utilization_by_job[job_id]["avg_nodes_consumed"].append(metric.avg_nodes_consumed)
                utilization_by_job[job_id]["p95_nodes_consumed"].append(metric.p95_nodes_consumed)
                utilization_by_job[job_id]["p99_nodes_consumed"].append(metric.p99_nodes_consumed)

            # Calculate averages and peaks
            result = []
            for job_id, data in utilization_by_job.items():
                result.append(
                    {
                        "job_id": job_id,
                        "avg_cpu_utilization_pct": sum(data["avg_cpu_utilization_pct"])
                        / len(data["avg_cpu_utilization_pct"]),
                        "avg_memory_utilization_pct": sum(data["avg_memory_utilization_pct"])
                        / len(data["avg_memory_utilization_pct"]),
                        "peak_cpu_utilization_pct": max(data["peak_cpu_utilization_pct"]),
                        "peak_memory_utilization_pct": max(data["peak_memory_utilization_pct"]),
                        "avg_nodes_consumed": sum(data["avg_nodes_consumed"])
                        / len(data["avg_nodes_consumed"]),
                        "p95_nodes_consumed": max(data["p95_nodes_consumed"]),  # Simplified
                        "p99_nodes_consumed": max(data["p99_nodes_consumed"]),  # Simplified
                    }
                )

            return result
        except Exception as e:
            logger.error("local_resource_utilization_error", error=str(e))
            return []

    def list_workspaces(self, start_date: str, end_date: str) -> List[Dict]:
        """List distinct workspaces with summary details from local CSV data."""
        logger.info("listing_workspaces_from_csv", start_date=start_date, end_date=end_date)
        try:
            df = pd.read_csv(self.csv_path)
            if "workspace_id" not in df.columns or "date" not in df.columns:
                return []

            df["workspace_id"] = df["workspace_id"].astype(str)
            if "workspace_name" in df.columns:
                df["workspace_name"] = df["workspace_name"].astype(str)
            else:
                df["workspace_name"] = df["workspace_id"]

            df["date"] = pd.to_datetime(df["date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df_filtered = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)].copy()
            if df_filtered.empty:
                return []

            if "job_id" in df_filtered.columns:
                df_filtered["job_id"] = df_filtered["job_id"].astype(str)
            else:
                df_filtered["job_id"] = None

            grouped = (
                df_filtered.groupby("workspace_id", dropna=False)
                .agg(
                    workspace_name=("workspace_name", "max"),
                    job_count=("job_id", lambda s: s.dropna().nunique()),
                    first_seen_date=("date", "min"),
                    last_seen_date=("date", "max"),
                )
                .reset_index()
            )
            grouped = grouped.sort_values(
                by=["last_seen_date", "workspace_id"], ascending=[False, True]
            )

            return [
                {
                    "workspace_id": (
                        str(row["workspace_id"]) if pd.notna(row["workspace_id"]) else "unknown"
                    ),
                    "workspace_name": (
                        str(row["workspace_name"])
                        if pd.notna(row["workspace_name"])
                        else (
                            str(row["workspace_id"]) if pd.notna(row["workspace_id"]) else "unknown"
                        )
                    ),
                    "job_count": int(row["job_count"]) if pd.notna(row["job_count"]) else 0,
                    "first_seen_date": (
                        row["first_seen_date"].strftime("%Y-%m-%d")
                        if pd.notna(row["first_seen_date"])
                        else None
                    ),
                    "last_seen_date": (
                        row["last_seen_date"].strftime("%Y-%m-%d")
                        if pd.notna(row["last_seen_date"])
                        else None
                    ),
                }
                for _, row in grouped.iterrows()
            ]
        except Exception as e:
            logger.error("list_workspaces_from_csv_error", error=str(e))
            raise

    def list_jobs_for_workspace(
        self, workspace_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """List aggregated jobs for a workspace from local CSV."""
        logger.info(
            "listing_jobs_for_workspace_from_csv",
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            df = pd.read_csv(self.csv_path)
            required_cols = {
                "workspace_id",
                "job_id",
                "date",
                "avg_cpu_utilization_pct",
                "avg_memory_utilization_pct",
                "job_duration_seconds",
                "current_node_type",
                "current_min_workers",
                "current_max_workers",
            }
            if not required_cols.issubset(set(df.columns)):
                return []

            df["workspace_id"] = df["workspace_id"].astype(str)
            df["job_id"] = df["job_id"].astype(str)
            df["date"] = pd.to_datetime(df["date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)

            df_filtered = df[
                (df["workspace_id"] == str(workspace_id))
                & (df["date"] >= start_dt)
                & (df["date"] <= end_dt)
            ].copy()
            if df_filtered.empty:
                return []

            if "job_name" not in df_filtered.columns:
                df_filtered["job_name"] = df_filtered["job_id"]
            if "workload_type" not in df_filtered.columns:
                df_filtered["workload_type"] = None

            grouped = (
                df_filtered.groupby("job_id", dropna=False)
                .agg(
                    job_name=("job_name", "max"),
                    workload_type=("workload_type", "max"),
                    avg_cpu_utilization_pct=("avg_cpu_utilization_pct", "mean"),
                    avg_memory_utilization_pct=("avg_memory_utilization_pct", "mean"),
                    total_runs=("job_id", "count"),
                    avg_duration_seconds=("job_duration_seconds", "mean"),
                    current_node_type=("current_node_type", "max"),
                    current_min_workers=("current_min_workers", "max"),
                    current_max_workers=("current_max_workers", "max"),
                    last_run_date=("date", "max"),
                )
                .reset_index()
                .sort_values(by=["job_name", "job_id"], ascending=[True, True])
            )

            return [
                {
                    "workspace_id": str(workspace_id),
                    "job_id": str(row["job_id"]),
                    "job_name": row["job_name"],
                    "workload_type": row["workload_type"],
                    "avg_cpu_utilization_pct": float(row["avg_cpu_utilization_pct"]),
                    "avg_memory_utilization_pct": float(row["avg_memory_utilization_pct"]),
                    "total_runs": int(row["total_runs"]),
                    "avg_duration_seconds": float(row["avg_duration_seconds"]),
                    "current_node_type": row["current_node_type"],
                    "current_min_workers": int(row["current_min_workers"]),
                    "current_max_workers": int(row["current_max_workers"]),
                    "last_run_date": row["last_run_date"].strftime("%Y-%m-%d"),
                }
                for _, row in grouped.iterrows()
            ]
        except Exception as e:
            logger.error(
                "list_jobs_for_workspace_from_csv_error",
                error=str(e),
                workspace_id=workspace_id,
            )
            raise

    def get_job_metrics(
        self, workspace_id: str, job_id: str, start_date: str, end_date: str
    ) -> Optional[Dict[str, Any]]:
        """Get aggregated metrics for one job/workspace from local CSV."""
        logger.info(
            "getting_job_metrics_from_csv",
            workspace_id=workspace_id,
            job_id=job_id,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            df = pd.read_csv(self.csv_path)
            required_cols = {
                "workspace_id",
                "job_id",
                "date",
                "job_duration_seconds",
                "total_cost_usd",
                "avg_cpu_utilization_pct",
                "avg_memory_utilization_pct",
                "peak_cpu_utilization_pct",
                "peak_memory_utilization_pct",
                "avg_nodes_consumed",
                "p95_nodes_consumed",
                "p99_nodes_consumed",
                "current_node_type",
                "current_min_workers",
                "current_max_workers",
            }
            if not required_cols.issubset(set(df.columns)):
                return None

            df["workspace_id"] = df["workspace_id"].astype(str)
            df["job_id"] = df["job_id"].astype(str)
            df["date"] = pd.to_datetime(df["date"])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df_filtered = df[
                (df["workspace_id"] == str(workspace_id))
                & (df["job_id"] == str(job_id))
                & (df["date"] >= start_dt)
                & (df["date"] <= end_dt)
            ].copy()
            if df_filtered.empty:
                return None

            first = df_filtered.iloc[0]
            last_run = df_filtered["date"].max()
            result: Dict[str, Any] = {
                "avg_duration_seconds": float(df_filtered["job_duration_seconds"].mean()),
                "avg_cost_usd": float(df_filtered["total_cost_usd"].mean()),
                "avg_cpu_utilization": float(df_filtered["avg_cpu_utilization_pct"].mean()),
                "avg_memory_utilization": float(df_filtered["avg_memory_utilization_pct"].mean()),
                "peak_cpu_utilization": float(df_filtered["peak_cpu_utilization_pct"].max()),
                "peak_memory_utilization": float(df_filtered["peak_memory_utilization_pct"].max()),
                "peak_cpu_utilization_pct": float(df_filtered["peak_cpu_utilization_pct"].max()),
                "peak_memory_utilization_pct": float(
                    df_filtered["peak_memory_utilization_pct"].max()
                ),
                "avg_nodes_consumed": float(df_filtered["avg_nodes_consumed"].mean()),
                "p95_nodes_consumed": float(df_filtered["p95_nodes_consumed"].quantile(0.95)),
                "p99_nodes_consumed": float(df_filtered["p99_nodes_consumed"].quantile(0.99)),
                "total_runs": int(len(df_filtered)),
                "current_node_type": first.get("current_node_type"),
                "current_min_workers": int(first.get("current_min_workers", 1)),
                "current_max_workers": int(first.get("current_max_workers", 16)),
                "last_run_date": last_run.strftime("%Y-%m-%d") if pd.notna(last_run) else None,
            }

            optional_map = (
                "job_name",
                "workspace_name",
                "job_date",
                "cluster_id",
                "start_time",
                "end_time",
                "delta_tables",
                "provisioning_efficiency_pct",
                "cpu_utilization_efficiency_pct",
                "memory_utilization_efficiency_pct",
                "max_nodes_provisioned",
                "total_cpus_provisioned",
                "total_memory_gb_provisioned",
                "workload_type",
            )
            for key in optional_map:
                if key in df_filtered.columns and pd.notna(first.get(key)):
                    result[key] = first.get(key)
            return result
        except Exception as e:
            logger.error(
                "get_job_metrics_from_csv_error",
                error=str(e),
                workspace_id=workspace_id,
                job_id=job_id,
            )
            raise

    def collect_cost_data(
        self, start_date: str, end_date: str, job_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """Collect cost and usage data from CSV.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            job_ids: Optional list of job IDs to filter

        Returns:
            List of dictionaries containing cost analysis
        """
        logger.info("collecting_cost_data_from_csv", start_date=start_date, end_date=end_date)

        try:
            # Get job metrics first
            metrics = self.collect_job_cluster_metrics(start_date, end_date, job_ids)

            if not metrics:
                return []

            # Aggregate cost data by job_id
            cost_by_job = {}
            for metric in metrics:
                job_id = metric.job_id
                if job_id not in cost_by_job:
                    cost_by_job[job_id] = {
                        "job_id": job_id,
                        "total_cost_usd": 0.0,
                        "cost_per_hour_usd": [],
                        "total_runs": 0,
                        "avg_cost_per_run": 0.0,
                    }

                cost_by_job[job_id]["total_cost_usd"] += metric.total_cost_usd
                cost_by_job[job_id]["cost_per_hour_usd"].append(metric.cost_per_hour_usd)
                cost_by_job[job_id]["total_runs"] += 1

            # Calculate averages
            result = []
            for job_id, data in cost_by_job.items():
                avg_cost_per_hour = (
                    sum(data["cost_per_hour_usd"]) / len(data["cost_per_hour_usd"])
                    if data["cost_per_hour_usd"]
                    else 0.0
                )
                avg_cost_per_run = (
                    data["total_cost_usd"] / data["total_runs"] if data["total_runs"] > 0 else 0.0
                )

                # Estimate monthly cost (assuming 30 days, 24 hours)
                monthly_cost = avg_cost_per_hour * 30 * 24

                result.append(
                    {
                        "job_id": job_id,
                        "total_cost_usd": data["total_cost_usd"],
                        "avg_cost_per_hour_usd": avg_cost_per_hour,
                        "avg_cost_per_run_usd": avg_cost_per_run,
                        "total_runs": data["total_runs"],
                        "monthly_cost": monthly_cost,
                    }
                )

            return result
        except Exception as e:
            logger.error("local_cost_data_error", error=str(e))
            return []
