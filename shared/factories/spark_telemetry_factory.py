"""Factory for Spark telemetry collectors (logs + metrics for RCA)."""

from __future__ import annotations

from typing import Any, Optional

from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def get_spark_telemetry_collector(settings: Optional[Settings] = None) -> Any:
    """Return local or Databricks spark telemetry collector from settings."""
    cfg = settings or default_settings
    logs_local = (cfg.local_spark_logs_path or "").strip()
    metrics_local = (cfg.local_spark_metrics_path or "").strip()
    logs_table = (cfg.databricks_spark_logs_table or "").strip()
    metrics_table = (cfg.databricks_spark_metrics_table or "").strip()

    # Prefer local fixtures when either local path is set and Delta tables are not.
    if (logs_local or metrics_local) and not (logs_table and metrics_table):
        from DE.src.collectors.local_spark_telemetry_collector import LocalSparkTelemetryCollector

        logger.info(
            "using_local_spark_telemetry_collector",
            logs_path=logs_local or None,
            metrics_path=metrics_local or None,
        )
        return LocalSparkTelemetryCollector(
            spark_logs_path=logs_local or None,
            spark_metrics_path=metrics_local or None,
            settings=cfg,
        )

    from DE.src.collectors.spark_telemetry_collector import SparkTelemetryCollector

    logger.info(
        "using_databricks_spark_telemetry_collector",
        logs_table=bool(logs_table),
        metrics_table=bool(metrics_table),
    )
    return SparkTelemetryCollector(settings=cfg)
