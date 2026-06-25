"""Job cluster metrics CSV schema — matches Databricks Delta table columns."""

from __future__ import annotations

import io
from typing import List, Optional, Set

import pandas as pd

from shared.models.job_cluster_metrics import DELTA_TABLE_COLUMNS

_READ_CSV_KWARGS = {"encoding": "utf-8-sig"}

CSV_COLUMNS: List[str] = list(DELTA_TABLE_COLUMNS)

REQUIRED_COLUMNS: Set[str] = {
    "job_run_date",
    "workspace_id",
    "job_id",
    "job_run_id",
    "cluster_id",
}

LOCAL_DATASET_KEY = "job_cluster_metrics"
STORED_FILENAME = "job_metrics.csv"
TEMPLATE_DOWNLOAD_NAME = "job_metrics_template.csv"


def validate_columns(columns: List[str]) -> List[str]:
    errors: List[str] = []
    normalized = {c.strip().lstrip("\ufeff") for c in columns if c and str(c).strip()}
    missing = REQUIRED_COLUMNS - normalized
    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")
    return errors


def get_template_csv_bytes() -> bytes:
    return (",".join(CSV_COLUMNS) + "\n").encode("utf-8")


def validate_upload_content(content: bytes) -> tuple[Optional[int], list[str]]:
    errors: list[str] = []
    try:
        df = pd.read_csv(io.BytesIO(content), nrows=5000, **_READ_CSV_KWARGS)
    except Exception as e:
        return None, [f"Could not parse CSV: {e}"]

    errors.extend(validate_columns(list(df.columns)))
    if df.empty:
        errors.append("CSV must contain at least one data row.")
    return len(df), errors
