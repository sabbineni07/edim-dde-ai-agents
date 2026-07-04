"""Local CSV data collector for testing and development."""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from shared.models.job_cluster_metrics import JobClusterMetrics
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Excel / some editors save CSV with BOM; strip so column names match ("date" not "\ufeffdate")
_READ_CSV_KWARGS = {"encoding": "utf-8-sig"}


def _json_safe_value(value: Any) -> Any:
    """Convert pandas/numpy scalars to native Python types for JSON/API responses."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, "item"):
        return value.item()
    if pd.isna(value):
        return None
    return value


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
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        job_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        job_run_id: Optional[str] = None,
    ) -> List[JobClusterMetrics]:
        """Collect job cluster metrics from CSV file.

        Args:
            start_date: Start date in YYYY-MM-DD format (optional when cluster_id is set)
            end_date: End date in YYYY-MM-DD format (optional when cluster_id is set)
            job_ids: Optional list of job IDs to filter
            workspace_id: Optional workspace ID to filter
            cluster_id: Optional cluster ID filter (per-cluster recommendations)
            job_run_id: Optional workflow job run ID filter

        Returns:
            List of JobClusterMetrics objects
        """
        run_only = bool(
            (cluster_id and str(cluster_id).strip()) or (job_run_id and str(job_run_id).strip())
        ) and not (start_date and end_date)
        logger.info(
            "collecting_job_cluster_metrics_from_csv",
            start_date=start_date,
            end_date=end_date,
            job_count=len(job_ids) if job_ids else None,
            cluster_id=cluster_id,
            job_run_id=job_run_id,
            run_only_lookup=run_only,
            csv_path=str(self.csv_path),
        )

        try:
            # Read CSV file
            df = pd.read_csv(self.csv_path, **_READ_CSV_KWARGS)
            logger.info("local_csv_loaded", rows=len(df), path=str(self.csv_path))

            # Normalize job_id and workspace_id to string for filtering (CSV may have numeric types)
            if "job_id" in df.columns:
                df["job_id"] = df["job_id"].astype(str)
            if "workspace_id" in df.columns:
                df["workspace_id"] = df["workspace_id"].astype(str)

            date_col = "job_run_date" if "job_run_date" in df.columns else "date"
            df[date_col] = pd.to_datetime(df[date_col])
            if run_only:
                df_filtered = df
            else:
                if not start_date or not end_date:
                    logger.warning("local_csv_missing_date_range")
                    return []
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df_filtered = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]
            logger.info(
                "local_csv_after_date_filter",
                rows=len(df_filtered),
                start=start_date,
                end=end_date,
                run_only_lookup=run_only,
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

            if cluster_id and "cluster_id" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["cluster_id"].astype(str) == str(cluster_id)]
            elif job_run_id and "job_run_id" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["job_run_id"].astype(str) == str(job_run_id)]

            df_filtered = df_filtered.copy()
            df_filtered[date_col] = df_filtered[date_col].dt.strftime("%Y-%m-%d")

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
                        elif (
                            key in ["workspace_id", "job_id", "cluster_id", "job_run_id"]
                            and value is not None
                        ):
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
                    first_record_date=rec.get("job_run_date") or rec.get("date"),
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
                    metric.avg_worker_cpu_utilization_pct
                )
                utilization_by_job[job_id]["avg_memory_utilization_pct"].append(
                    metric.avg_worker_memory_utilization_pct
                )
                utilization_by_job[job_id]["peak_cpu_utilization_pct"].append(
                    metric.peak_worker_cpu_utilization_pct
                )
                utilization_by_job[job_id]["peak_memory_utilization_pct"].append(
                    metric.peak_worker_memory_utilization_pct
                )
                utilization_by_job[job_id]["avg_nodes_consumed"].append(
                    metric.avg_worker_nodes_consumed
                )
                utilization_by_job[job_id]["p95_nodes_consumed"].append(
                    metric.avg_worker_nodes_consumed
                )
                utilization_by_job[job_id]["p99_nodes_consumed"].append(
                    metric.p99_worker_nodes_consumed
                )

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

    def list_workspaces(self) -> List[Dict]:
        """List distinct workspaces with summary details from local CSV data."""
        logger.info("listing_workspaces_from_csv")
        try:
            df = pd.read_csv(self.csv_path, **_READ_CSV_KWARGS)
            date_col = "job_run_date" if "job_run_date" in df.columns else "date"
            if "workspace_id" not in df.columns or date_col not in df.columns:
                return []

            df["workspace_id"] = df["workspace_id"].astype(str)
            if "workspace_name" in df.columns:
                df["workspace_name"] = df["workspace_name"].astype(str)
            else:
                df["workspace_name"] = df["workspace_id"]

            df[date_col] = pd.to_datetime(df[date_col])
            if df.empty:
                return []

            if "job_id" in df.columns:
                df["job_id"] = df["job_id"].astype(str)
            else:
                df["job_id"] = None

            grouped = (
                df.groupby("workspace_id", dropna=False)
                .agg(
                    workspace_name=("workspace_name", "max"),
                    job_count=("job_id", lambda s: s.dropna().nunique()),
                    first_seen_date=(date_col, "min"),
                    last_seen_date=(date_col, "max"),
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
            df = pd.read_csv(self.csv_path, **_READ_CSV_KWARGS)
            date_col = "job_run_date" if "job_run_date" in df.columns else "date"
            required_cols = {
                "workspace_id",
                "job_id",
                date_col,
                "avg_worker_cpu_utilization_pct",
                "avg_worker_memory_utilization_pct",
                "job_run_duration_seconds",
                "azure_worker_vm_size",
                "max_worker_nodes_provisioned",
            }
            if not required_cols.issubset(set(df.columns)):
                return []

            df["workspace_id"] = df["workspace_id"].astype(str)
            df["job_id"] = df["job_id"].astype(str)
            df[date_col] = pd.to_datetime(df[date_col])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)

            df_filtered = df[
                (df["workspace_id"] == str(workspace_id))
                & (df[date_col] >= start_dt)
                & (df[date_col] <= end_dt)
            ].copy()
            if df_filtered.empty:
                return []

            if "job_name" not in df_filtered.columns:
                df_filtered["job_name"] = df_filtered["job_id"]
            if "job_type" not in df_filtered.columns:
                df_filtered["job_type"] = None
            if "dbr_version" not in df_filtered.columns:
                df_filtered["dbr_version"] = None

            grouped = (
                df_filtered.groupby("job_id", dropna=False)
                .agg(
                    job_name=("job_name", "max"),
                    workload_type=("job_type", "max"),
                    avg_cpu_utilization_pct=("avg_worker_cpu_utilization_pct", "mean"),
                    avg_memory_utilization_pct=("avg_worker_memory_utilization_pct", "mean"),
                    total_runs=("job_id", "count"),
                    avg_duration_seconds=("job_run_duration_seconds", "mean"),
                    current_node_type=("azure_worker_vm_size", "max"),
                    current_max_workers=("max_worker_nodes_provisioned", "max"),
                    last_run_date=(date_col, "max"),
                    dbr_version=("dbr_version", "max"),
                )
                .reset_index()
                .sort_values(by=["job_name", "job_id"], ascending=[True, True])
            )

            return [
                {
                    "workspace_id": str(workspace_id),
                    "job_id": str(row["job_id"]),
                    "job_name": row["job_name"],
                    "job_type": row["workload_type"],
                    "avg_worker_cpu_utilization_pct": float(row["avg_cpu_utilization_pct"]),
                    "avg_worker_memory_utilization_pct": float(row["avg_memory_utilization_pct"]),
                    "total_runs": int(row["total_runs"]),
                    "avg_job_run_duration_seconds": float(row["avg_duration_seconds"]),
                    "azure_worker_vm_size": row["current_node_type"],
                    "max_worker_nodes_provisioned": int(row["current_max_workers"]),
                    "last_job_run_date": row["last_run_date"].strftime("%Y-%m-%d"),
                    "dbr_version": (
                        str(row["dbr_version"]) if pd.notna(row.get("dbr_version")) else None
                    ),
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

    def list_job_runs(
        self, workspace_id: str, job_id: str, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """List distinct job runs for a job in a workspace within the date range."""
        logger.info(
            "listing_job_runs_from_csv",
            workspace_id=workspace_id,
            job_id=job_id,
            start_date=start_date,
            end_date=end_date,
        )
        try:
            df = pd.read_csv(self.csv_path, **_READ_CSV_KWARGS)
            date_col = "job_run_date" if "job_run_date" in df.columns else "date"
            if "cluster_id" not in df.columns:
                return []

            df["workspace_id"] = df["workspace_id"].astype(str)
            df["job_id"] = df["job_id"].astype(str)
            df["cluster_id"] = df["cluster_id"].astype(str)
            if "job_run_id" in df.columns:
                df["job_run_id"] = df["job_run_id"].astype(str)
            df[date_col] = pd.to_datetime(df[date_col])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df_filtered = df[
                (df["workspace_id"] == str(workspace_id))
                & (df["job_id"] == str(job_id))
                & (df[date_col] >= start_dt)
                & (df[date_col] <= end_dt)
            ].copy()
            if df_filtered.empty:
                return []

            if "dbr_version" not in df_filtered.columns:
                df_filtered["dbr_version"] = None

            runs: List[Dict[str, Any]] = []
            for cluster_id, group in df_filtered.groupby("cluster_id", sort=False):
                first = group.iloc[0]
                last_date = group[date_col].max()
                job_run_id_val = first.get("job_run_id")
                runs.append(
                    {
                        "cluster_id": str(cluster_id),
                        "job_run_id": str(job_run_id_val) if job_run_id_val is not None else None,
                        "job_run_date": (
                            last_date.strftime("%Y-%m-%d") if pd.notna(last_date) else None
                        ),
                        "job_run_duration_seconds": float(
                            group["job_run_duration_seconds"].iloc[0]
                        ),
                        "azure_driver_vm_size": first.get("azure_driver_vm_size"),
                        "driver_node_count": int(first.get("driver_node_count", 1)),
                        "avg_driver_cpu_utilization_pct": (
                            float(group["avg_driver_cpu_utilization_pct"].mean())
                            if "avg_driver_cpu_utilization_pct" in group.columns
                            else None
                        ),
                        "avg_driver_memory_utilization_pct": (
                            float(group["avg_driver_memory_utilization_pct"].mean())
                            if "avg_driver_memory_utilization_pct" in group.columns
                            else None
                        ),
                        "peak_driver_cpu_utilization_pct": (
                            float(group["peak_driver_cpu_utilization_pct"].max())
                            if "peak_driver_cpu_utilization_pct" in group.columns
                            else None
                        ),
                        "avg_worker_cpu_utilization_pct": float(
                            group["avg_worker_cpu_utilization_pct"].mean()
                        ),
                        "avg_worker_memory_utilization_pct": float(
                            group["avg_worker_memory_utilization_pct"].mean()
                        ),
                        "avg_worker_nodes_consumed": float(
                            group["avg_worker_nodes_consumed"].mean()
                        ),
                        "total_worker_vcpus_provisioned": (
                            float(group["total_worker_vcpus_provisioned"].iloc[0])
                            if "total_worker_vcpus_provisioned" in group.columns
                            else None
                        ),
                        "total_worker_memory_gb_provisioned": (
                            float(group["total_worker_memory_gb_provisioned"].iloc[0])
                            if "total_worker_memory_gb_provisioned" in group.columns
                            else None
                        ),
                        "peak_worker_cpu_utilization_pct": float(
                            group["peak_worker_cpu_utilization_pct"].max()
                        ),
                        "peak_worker_memory_utilization_pct": float(
                            group["peak_worker_memory_utilization_pct"].max()
                        ),
                        "azure_worker_vm_size": first.get("azure_worker_vm_size"),
                        "max_worker_nodes_provisioned": int(
                            first.get("max_worker_nodes_provisioned", 16)
                        ),
                        "job_type": first.get("job_type"),
                        "dbr_version": (
                            str(first.get("dbr_version"))
                            if first.get("dbr_version") is not None
                            and pd.notna(first.get("dbr_version"))
                            else None
                        ),
                    }
                )

            runs.sort(key=lambda r: (r.get("job_run_date") or "", r["cluster_id"]), reverse=True)
            return runs
        except Exception as e:
            logger.error(
                "list_job_runs_from_csv_error",
                error=str(e),
                workspace_id=workspace_id,
                job_id=job_id,
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
            df = pd.read_csv(self.csv_path, **_READ_CSV_KWARGS)
            date_col = "job_run_date" if "job_run_date" in df.columns else "date"
            required_cols = {
                "workspace_id",
                "job_id",
                date_col,
                "job_run_duration_seconds",
                "avg_worker_cpu_utilization_pct",
                "avg_worker_memory_utilization_pct",
                "peak_worker_cpu_utilization_pct",
                "peak_worker_memory_utilization_pct",
                "avg_worker_nodes_consumed",
                "p99_worker_nodes_consumed",
                "azure_worker_vm_size",
                "max_worker_nodes_provisioned",
            }
            if not required_cols.issubset(set(df.columns)):
                return None

            df["workspace_id"] = df["workspace_id"].astype(str)
            df["job_id"] = df["job_id"].astype(str)
            df[date_col] = pd.to_datetime(df[date_col])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df_filtered = df[
                (df["workspace_id"] == str(workspace_id))
                & (df["job_id"] == str(job_id))
                & (df[date_col] >= start_dt)
                & (df[date_col] <= end_dt)
            ].copy()
            if df_filtered.empty:
                return None

            first = df_filtered.iloc[0]
            last_run = df_filtered[date_col].max()
            result: Dict[str, Any] = {
                "avg_job_run_duration_seconds": float(
                    df_filtered["job_run_duration_seconds"].mean()
                ),
                "azure_driver_vm_size": first.get("azure_driver_vm_size"),
                "driver_node_count": int(first.get("driver_node_count", 1)),
                "avg_driver_cpu_utilization_pct": (
                    float(df_filtered["avg_driver_cpu_utilization_pct"].mean())
                    if "avg_driver_cpu_utilization_pct" in df_filtered.columns
                    else None
                ),
                "avg_driver_memory_utilization_pct": (
                    float(df_filtered["avg_driver_memory_utilization_pct"].mean())
                    if "avg_driver_memory_utilization_pct" in df_filtered.columns
                    else None
                ),
                "peak_driver_cpu_utilization_pct": (
                    float(df_filtered["peak_driver_cpu_utilization_pct"].max())
                    if "peak_driver_cpu_utilization_pct" in df_filtered.columns
                    else None
                ),
                "avg_driver_vcpus_consumed": (
                    float(df_filtered["driver_vcpus_consumed"].mean())
                    if "driver_vcpus_consumed" in df_filtered.columns
                    else None
                ),
                "avg_driver_memory_gb_consumed": (
                    float(df_filtered["driver_memory_gb_consumed"].mean())
                    if "driver_memory_gb_consumed" in df_filtered.columns
                    else None
                ),
                "avg_worker_cpu_utilization_pct": float(
                    df_filtered["avg_worker_cpu_utilization_pct"].mean()
                ),
                "avg_worker_memory_utilization_pct": float(
                    df_filtered["avg_worker_memory_utilization_pct"].mean()
                ),
                "peak_worker_cpu_utilization_pct": float(
                    df_filtered["peak_worker_cpu_utilization_pct"].max()
                ),
                "peak_worker_memory_utilization_pct": float(
                    df_filtered["peak_worker_memory_utilization_pct"].max()
                ),
                "avg_worker_nodes_consumed": float(df_filtered["avg_worker_nodes_consumed"].mean()),
                "p95_worker_nodes_consumed": float(
                    df_filtered["avg_worker_nodes_consumed"].quantile(0.95)
                ),
                "avg_total_worker_vcpus_provisioned": (
                    float(df_filtered["total_worker_vcpus_provisioned"].mean())
                    if "total_worker_vcpus_provisioned" in df_filtered.columns
                    else None
                ),
                "avg_total_worker_memory_gb_provisioned": (
                    float(df_filtered["total_worker_memory_gb_provisioned"].mean())
                    if "total_worker_memory_gb_provisioned" in df_filtered.columns
                    else None
                ),
                "p99_worker_nodes_consumed": float(
                    df_filtered["p99_worker_nodes_consumed"].quantile(0.99)
                ),
                "total_runs": int(len(df_filtered)),
                "azure_worker_vm_size": first.get("azure_worker_vm_size"),
                "max_worker_nodes_provisioned": int(first.get("max_worker_nodes_provisioned", 16)),
                "last_job_run_date": last_run.strftime("%Y-%m-%d") if pd.notna(last_run) else None,
            }

            optional_map = (
                "job_name",
                "dbr_version",
                "workspace_name",
                "job_run_date",
                "cluster_id",
                "job_run_start_time_utc",
                "job_run_end_time_utc",
                "azure_driver_vm_size",
                "driver_node_count",
                "driver_vcpus_consumed",
                "driver_memory_gb_consumed",
                "delta_tables_ingested",
                "worker_node_provisioning_efficiency_pct",
                "worker_cpu_utilization_efficiency_pct",
                "worker_memory_utilization_efficiency_pct",
                "max_worker_nodes_provisioned",
                "avg_worker_vcpus_consumed",
                "avg_worker_memory_gb_consumed",
                "job_type",
                "processed_row_count",
                "processed_bytes",
            )
            for key in optional_map:
                if key in df_filtered.columns and pd.notna(first.get(key)):
                    result[key] = _json_safe_value(first.get(key))
            return {k: _json_safe_value(v) for k, v in result.items()}
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

                cost_by_job[job_id]["total_runs"] += 1

            # Calculate averages
            result = []
            for job_id, data in cost_by_job.items():
                result.append(
                    {
                        "job_id": job_id,
                        "total_cost_usd": 0.0,
                        "avg_cost_per_hour_usd": 0.0,
                        "avg_cost_per_run_usd": 0.0,
                        "total_runs": data["total_runs"],
                        "monthly_cost": 0.0,
                    }
                )

            return result
        except Exception as e:
            logger.error("local_cost_data_error", error=str(e))
            return []
