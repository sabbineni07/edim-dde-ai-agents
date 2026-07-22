"""Collect Spark logs and metrics telemetry from Delta tables for RCA."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from databricks import sql

from shared.config.settings import Settings
from shared.config.settings import settings as default_settings
from shared.rca.evidence_pack import assemble_evidence_pack_for_run
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_sql_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _rows_to_dicts(columns: List[str], rows: List[Any]) -> List[Dict[str, Any]]:
    return [{col: _normalize_sql_value(val) for col, val in zip(columns, row)} for row in rows]


class SparkTelemetryCollector:
    """Read spark_logs and spark_metrics Delta tables via Databricks SQL warehouse."""

    def __init__(
        self,
        *,
        spark_logs_table: Optional[str] = None,
        spark_metrics_table: Optional[str] = None,
        server_hostname: Optional[str] = None,
        http_path: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        from shared.databricks.sql_config import normalize_databricks_sql_config

        cfg = settings or default_settings
        sql_cfg = normalize_databricks_sql_config(
            {
                "databricks_server_hostname": server_hostname or cfg.databricks_server_hostname,
                "databricks_http_path": http_path or cfg.databricks_http_path,
            },
            databricks_host=cfg.databricks_host,
        )
        self._logs_table = (
            spark_logs_table or cfg.databricks_spark_logs_table or ""
        ).strip() or None
        self._metrics_table = (
            spark_metrics_table or cfg.databricks_spark_metrics_table or ""
        ).strip() or None
        self._server_hostname = sql_cfg["databricks_server_hostname"]
        self._http_path = sql_cfg["databricks_http_path"]

    def _connection_params(self) -> Dict[str, Any]:
        from shared.auth.databricks_tokens import resolve_databricks_sql_access_token

        if not (self._server_hostname and self._http_path):
            raise RuntimeError(
                "Databricks SQL connection is not configured "
                f"(hostname={self._server_hostname!r}, http_path={self._http_path!r})."
            )
        token = resolve_databricks_sql_access_token()
        if not token:
            raise RuntimeError(
                "No Databricks SQL access token available. On Databricks Apps, attach a "
                "sql-warehouse resource; locally use az login or DATABRICKS_TOKEN."
            )
        return {
            "server_hostname": self._server_hostname,
            "http_path": self._http_path,
            "access_token": token,
            "_socket_timeout": 300,
            "_query_timeout": 0,
        }

    def _execute(self, query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        with sql.connect(**self._connection_params()) as conn:
            with conn.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
                return _rows_to_dicts(columns, rows)

    def get_failure_anchors(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Failed pipeline_end anchors (SQL errors come from get_sql_plans)."""
        table = self._metrics_table
        if not table:
            logger.warning("spark_metrics_table_not_set")
            return []
        clauses = [
            "CAST(job_run_id AS STRING) = ?",
            "event_type = 'pipeline_end'",
            "(successful = false OR lower(CAST(status AS STRING)) IN ('failure', 'failed', 'error'))",
        ]
        params: List[Any] = [job_run_id]
        if job_run_date:
            clauses.append("job_run_date = CAST(? AS DATE)")
            params.append(job_run_date)
        if task_key:
            clauses.append("CAST(task_key AS STRING) = ?")
            params.append(task_key)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(event_id AS STRING) AS event_id,
          CAST(event_ts AS STRING) AS event_ts,
          event_type,
          CAST(job_id AS STRING) AS job_id,
          CAST(job_run_id AS STRING) AS job_run_id,
          CAST(job_run_date AS STRING) AS job_run_date,
          CAST(task_key AS STRING) AS task_key,
          CAST(spark_app_id AS STRING) AS spark_app_id,
          status,
          successful,
          failure_reason,
          CAST(attributes AS STRING) AS attributes
        FROM {table}
        WHERE {where}
        ORDER BY event_ts DESC
        LIMIT 20
        """
        return self._execute(query, params)

    def get_sql_plans(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """SQL error/observed events; plan fields live in attributes (parsed in pack builder)."""
        table = self._metrics_table
        if not table:
            return []
        clauses = [
            "CAST(job_run_id AS STRING) = ?",
            "event_type IN ('spark_sql_query_error', 'spark_sql_query_observed')",
        ]
        params: List[Any] = [job_run_id]
        if job_run_date:
            clauses.append("job_run_date = CAST(? AS DATE)")
            params.append(job_run_date)
        if task_key:
            clauses.append("CAST(task_key AS STRING) = ?")
            params.append(task_key)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(event_id AS STRING) AS event_id,
          CAST(event_ts AS STRING) AS event_ts,
          event_type,
          CAST(job_id AS STRING) AS job_id,
          CAST(job_run_id AS STRING) AS job_run_id,
          CAST(job_run_date AS STRING) AS job_run_date,
          CAST(task_key AS STRING) AS task_key,
          CAST(spark_app_id AS STRING) AS spark_app_id,
          status,
          successful,
          failure_reason,
          CAST(attributes AS STRING) AS attributes
        FROM {table}
        WHERE {where}
        ORDER BY
          CASE WHEN event_type = 'spark_sql_query_error' THEN 0 ELSE 1 END,
          event_ts DESC
        LIMIT 40
        """
        return self._execute(query, params)

    def get_stage_pressure(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        table = self._metrics_table
        if not table:
            return []
        clauses = [
            "CAST(job_run_id AS STRING) = ?",
            "event_type IN ("
            "'spark_job_completed', 'spark_stage_completed', "
            "'spark_stage_task_summary')",
        ]
        params: List[Any] = [job_run_id]
        if job_run_date:
            clauses.append("job_run_date = CAST(? AS DATE)")
            params.append(job_run_date)
        if task_key:
            clauses.append("CAST(task_key AS STRING) = ?")
            params.append(task_key)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(event_id AS STRING) AS event_id,
          CAST(event_ts AS STRING) AS event_ts,
          event_type,
          CAST(task_key AS STRING) AS task_key,
          status,
          successful,
          failure_reason,
          CAST(attributes AS STRING) AS attributes
        FROM {table}
        WHERE {where}
        ORDER BY event_ts DESC
        LIMIT 100
        """
        rows = self._execute(query, params)
        # Prefer rows that look failed or have failed tasks
        prioritized: List[Dict[str, Any]] = []
        other: List[Dict[str, Any]] = []
        for row in rows:
            attrs_raw = row.get("attributes") or "{}"
            try:
                attrs = json.loads(attrs_raw) if isinstance(attrs_raw, str) else (attrs_raw or {})
            except json.JSONDecodeError:
                attrs = {}
            status = str(attrs.get("status") or row.get("status") or "").lower()
            failed_tasks = attrs.get("num_failed_tasks") or 0
            try:
                failed_n = int(failed_tasks)
            except (TypeError, ValueError):
                failed_n = 0
            if "fail" in status or failed_n > 0 or row.get("successful") is False:
                prioritized.append(row)
            else:
                other.append(row)
        return (prioritized + other)[:40]

    def get_error_logs(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        table = self._logs_table
        if not table:
            logger.warning("spark_logs_table_not_set")
            return []
        clauses = [
            "CAST(job_run_id AS STRING) = ?",
            "(upper(log_level) IN ('ERROR', 'WARNING') OR exception IS NOT NULL)",
        ]
        params: List[Any] = [job_run_id]
        if job_run_date:
            clauses.append("job_run_date = CAST(? AS DATE)")
            params.append(job_run_date)
        if task_key:
            clauses.append("CAST(task_key AS STRING) = ?")
            params.append(task_key)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(log_timestamp AS STRING) AS log_timestamp,
          log_level,
          logger_name,
          message,
          exception,
          CAST(job_id AS STRING) AS job_id,
          CAST(job_run_id AS STRING) AS job_run_id,
          CAST(job_run_date AS STRING) AS job_run_date,
          CAST(task_key AS STRING) AS task_key,
          CAST(spark_app_id AS STRING) AS spark_app_id
        FROM {table}
        WHERE {where}
        ORDER BY log_timestamp DESC
        LIMIT 100
        """
        return self._execute(query, params)

    def get_timeline(
        self,
        *,
        job_run_id: str,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        table = self._metrics_table
        if not table:
            return []
        clauses = ["CAST(job_run_id AS STRING) = ?"]
        params: List[Any] = [job_run_id]
        if job_run_date:
            clauses.append("job_run_date = CAST(? AS DATE)")
            params.append(job_run_date)
        if task_key:
            clauses.append("CAST(task_key AS STRING) = ?")
            params.append(task_key)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(event_id AS STRING) AS event_id,
          CAST(event_ts AS STRING) AS event_ts,
          event_type,
          CAST(task_key AS STRING) AS task_key,
          status,
          successful,
          failure_reason,
          CAST(attributes AS STRING) AS attributes
        FROM {table}
        WHERE {where}
          AND event_type IN (
            'pipeline_start', 'pipeline_end',
            'spark_sql_query_observed', 'spark_sql_query_error',
            'spark_job_start', 'spark_job_completed',
            'spark_stage_start', 'spark_stage_completed'
          )
        ORDER BY event_ts ASC
        LIMIT 80
        """
        return self._execute(query, params)

    def list_failed_runs(
        self,
        *,
        job_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        table = self._metrics_table
        if not table:
            logger.warning("spark_metrics_table_not_set")
            return []
        clauses = [
            "CAST(job_id AS STRING) = ?",
            "("
            "  (event_type = 'pipeline_end' AND "
            "   (successful = false OR lower(CAST(status AS STRING)) IN ('failure', 'failed', 'error')))"
            "  OR event_type = 'spark_sql_query_error'"
            ")",
        ]
        params: List[Any] = [job_id]
        if start_date:
            clauses.append("job_run_date >= CAST(? AS DATE)")
            params.append(start_date)
        if end_date:
            clauses.append("job_run_date <= CAST(? AS DATE)")
            params.append(end_date)
        where = " AND ".join(clauses)
        query = f"""
        SELECT
          CAST(job_id AS STRING) AS job_id,
          CAST(job_run_id AS STRING) AS job_run_id,
          CAST(job_run_date AS STRING) AS job_run_date,
          CAST(task_key AS STRING) AS task_key,
          job_name,
          pipeline,
          CAST(workspace_id AS STRING) AS workspace_id,
          workspace_name,
          max(CAST(event_ts AS STRING)) AS last_event_ts,
          max(failure_reason) AS failure_reason,
          count(*) AS failure_event_count
        FROM {table}
        WHERE {where}
        GROUP BY
          CAST(job_id AS STRING),
          CAST(job_run_id AS STRING),
          CAST(job_run_date AS STRING),
          CAST(task_key AS STRING),
          job_name,
          pipeline,
          CAST(workspace_id AS STRING),
          workspace_name
        ORDER BY last_event_ts DESC
        LIMIT {int(limit)}
        """
        return self._execute(query, params)

    def build_evidence_pack_for_run(
        self,
        *,
        job_run_id: str,
        job_id: Optional[str] = None,
        job_run_date: Optional[str] = None,
        task_key: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return assemble_evidence_pack_for_run(
            self,
            job_run_id=job_run_id,
            job_id=job_id,
            job_run_date=job_run_date,
            task_key=task_key,
            workspace_id=workspace_id,
        )
