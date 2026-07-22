"""TEMPORARY: ad-hoc Postgres SQL executor for local/admin debugging.

Remove later by deleting this file and the matching include in API/src/main.py,
plus UI feature `temp-sql-executor` and its route/menu wiring.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from shared.auth.admin import is_admin
from shared.database.connection import get_database_session
from shared.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

_MAX_ROWS = 500
_MAX_SQL_CHARS = 50_000


class TempSqlExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=_MAX_SQL_CHARS)
    max_rows: int = Field(default=_MAX_ROWS, ge=1, le=_MAX_ROWS)


class TempSqlExecuteResponse(BaseModel):
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    returns_rows: bool = False
    elapsed_ms: int = 0
    message: str = ""


def _user_id(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    return (x_user_id or x_user_name or "anonymous").strip() or "anonymous"


def _require_admin(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    user = _user_id(x_user_name, x_user_id)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


@router.post("/execute", response_model=TempSqlExecuteResponse)
def execute_sql(
    body: TempSqlExecuteRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> TempSqlExecuteResponse:
    """Run a single SQL statement against the app Postgres database."""
    user = _require_admin(x_user_name, x_user_id)
    sql = (body.sql or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL is required")
    if ";" in sql.rstrip().rstrip(";"):
        raise HTTPException(
            status_code=400,
            detail="Only a single SQL statement is allowed (no multi-statement batches)",
        )

    max_rows = min(body.max_rows, _MAX_ROWS)
    started = time.perf_counter()
    session = get_database_session()
    try:
        result = session.execute(text(sql))
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if result.returns_rows:
            columns = list(result.keys())
            raw_rows = result.fetchmany(max_rows + 1)
            truncated = len(raw_rows) > max_rows
            rows = [[_jsonable(v) for v in row] for row in raw_rows[:max_rows]]
            session.commit()
            logger.info(
                "temp_sql_executor_select",
                user=user,
                row_count=len(rows),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
            return TempSqlExecuteResponse(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                returns_rows=True,
                elapsed_ms=elapsed_ms,
                message=(f"Returned {len(rows)} row(s)" + (" (truncated)" if truncated else "")),
            )

        # DML / DDL / etc.
        affected = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
        session.commit()
        logger.info(
            "temp_sql_executor_mutate",
            user=user,
            rowcount=affected,
            elapsed_ms=elapsed_ms,
        )
        return TempSqlExecuteResponse(
            columns=[],
            rows=[],
            row_count=affected,
            truncated=False,
            returns_rows=False,
            elapsed_ms=elapsed_ms,
            message=f"Statement OK — {affected} row(s) affected",
        )
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.warning("temp_sql_executor_failed", user=user, error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        session.close()
