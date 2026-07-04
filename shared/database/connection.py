"""Database connection management."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Optional, Tuple
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
_oauth_token: Optional[str] = None
_oauth_token_expiry: float = 0.0


def postgres_backend() -> str:
    """Return normalized Postgres backend: ``local`` or ``lakebase``."""
    return (settings.postgres_backend or "local").strip().lower()


def use_lakebase_oauth() -> bool:
    """True when Postgres is enabled and configured for Lakebase OAuth."""
    return settings.use_postgres and postgres_backend() == "lakebase"


def _local_postgres_url() -> str:
    host = settings.postgres_host or "localhost"
    port = settings.postgres_port
    user = quote_plus(settings.postgres_user or "postgres")
    password = quote_plus(settings.postgres_password or "postgres")
    database = settings.postgres_database or "ai_agents"
    ssl_mode = settings.postgres_ssl_mode
    if ssl_mode == "disable":
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"


def _lakebase_postgres_url() -> str:
    if not settings.postgres_host:
        raise ValueError("POSTGRES_HOST is required when POSTGRES_BACKEND=lakebase")
    if not settings.postgres_user:
        raise ValueError("POSTGRES_USER is required when POSTGRES_BACKEND=lakebase")
    if not settings.postgres_lakebase_endpoint:
        raise ValueError(
            "POSTGRES_LAKEBASE_ENDPOINT is required when POSTGRES_BACKEND=lakebase "
            "(format: projects/<project>/branches/<branch>/endpoints/<endpoint>)"
        )

    host = settings.postgres_host
    port = settings.postgres_port
    user = quote_plus(settings.postgres_user)
    database = settings.postgres_database or "databricks_postgres"
    ssl_mode = settings.postgres_ssl_mode or "require"
    return f"postgresql+psycopg2://{user}:@{host}:{port}/{database}?sslmode={ssl_mode}"


def get_database_url() -> str:
    if settings.use_postgres:
        if use_lakebase_oauth():
            return _lakebase_postgres_url()
        return _local_postgres_url()

    if not settings.azure_sql_server:
        raise ValueError("Azure SQL Server configuration not provided")
    server = settings.azure_sql_server
    database = settings.azure_sql_database
    username = settings.azure_sql_username
    password = settings.azure_sql_password
    return (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}"
        f"?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )


def _is_databricks_app_runtime() -> bool:
    return bool(os.environ.get("DATABRICKS_APP_NAME"))


def _databricks_workspace_host() -> Optional[str]:
    from shared.databricks.workspace_client import databricks_workspace_host_from_settings

    return databricks_workspace_host_from_settings(settings)


def _get_workspace_client():
    from shared.databricks.workspace_client import get_workspace_client_for_settings

    return get_workspace_client_for_settings(settings)


def _parse_credential_expiry(expire_time: Any) -> float:
    if expire_time is None:
        return time.time() + 3600
    if hasattr(expire_time, "timestamp"):
        return float(expire_time.timestamp())
    if isinstance(expire_time, str):
        normalized = expire_time.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    if hasattr(expire_time, "seconds"):
        return float(expire_time.seconds)
    return time.time() + 3600


def _generate_lakebase_database_credential(endpoint: str) -> Tuple[str, Any]:
    """Mint a Lakebase OAuth password token for the given endpoint path."""
    client = _get_workspace_client()

    postgres_api = getattr(client, "postgres", None)
    if postgres_api is not None:
        credential = postgres_api.generate_database_credential(endpoint=endpoint)
        return credential.token, credential.expire_time

    try:
        from databricks.sdk.service.postgres import PostgresAPI

        postgres_api = PostgresAPI(client.api_client)
        credential = postgres_api.generate_database_credential(endpoint=endpoint)
        return credential.token, credential.expire_time
    except (ImportError, AttributeError) as exc:
        logger.debug("lakebase_postgres_api_unavailable", error=str(exc))

    logger.info("lakebase_oauth_using_rest_fallback", endpoint=endpoint)
    response = client.api_client.do(
        "POST",
        "/api/2.0/postgres/credentials",
        body={"endpoint": endpoint},
    )
    if not isinstance(response, dict) or not response.get("token"):
        raise RuntimeError("Lakebase credential API returned no token")
    return response["token"], response.get("expire_time")


def _refresh_oauth_token() -> str:
    global _oauth_token, _oauth_token_expiry

    if _oauth_token is not None and time.time() < _oauth_token_expiry - 120:
        return _oauth_token

    endpoint = settings.postgres_lakebase_endpoint
    if not endpoint:
        raise ValueError("POSTGRES_LAKEBASE_ENDPOINT is required for Lakebase OAuth")

    token, expire_time = _generate_lakebase_database_credential(endpoint)
    _oauth_token = token
    _oauth_token_expiry = _parse_credential_expiry(expire_time)
    logger.debug(
        "lakebase_oauth_token_refreshed",
        endpoint=endpoint,
        expires_at=str(expire_time),
    )
    return _oauth_token


def _attach_lakebase_oauth_listener(engine: Engine) -> None:
    @event.listens_for(engine, "do_connect")
    def provide_oauth_token(dialect, conn_rec, cargs, cparams):
        cparams["password"] = _refresh_oauth_token()


def get_database_engine() -> Engine:
    global _engine
    if _engine is None:
        database_url = get_database_url()
        if settings.use_postgres:
            _engine = create_engine(
                database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=settings.app_env == "development",
            )
            if use_lakebase_oauth():
                _attach_lakebase_oauth_listener(_engine)
        else:
            _engine = create_engine(
                database_url, poolclass=NullPool, echo=settings.app_env == "development"
            )
        logger.info(
            "database_engine_created",
            database_type="postgresql" if settings.use_postgres else "sqlserver",
            postgres_backend=postgres_backend() if settings.use_postgres else None,
        )
    return _engine


def get_database_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_database_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal()


def reset_database_connection() -> None:
    """Clear cached engine/session state (tests)."""
    global _engine, _SessionLocal, _oauth_token, _oauth_token_expiry
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _oauth_token = None
    _oauth_token_expiry = 0.0


def _is_insufficient_privilege_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if "insufficientprivilege" in text or "permission denied for schema" in text:
        return True
    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        return _is_insufficient_privilege_error(orig)
    return False


def _lakebase_privilege_setup_hint() -> str:
    user = settings.postgres_user or "<PGUSER / DATABRICKS_CLIENT_ID>"
    return (
        f"Lakebase OAuth role {user!r} cannot CREATE objects in schema public. "
        "Run scripts/lakebase_bootstrap_grants.sql in the Lakebase SQL Editor "
        "(as a database owner), replacing <DATABRICKS_CLIENT_ID> with the app "
        "service principal client ID, then redeploy the app."
    )


def init_database():
    from shared.database.models import Base

    engine = get_database_engine()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        if use_lakebase_oauth() and _is_insufficient_privilege_error(exc):
            raise RuntimeError(_lakebase_privilege_setup_hint()) from exc
        raise
    logger.info("database_tables_initialized")
    try:
        from shared.services.platform_environment_service import seed_platform_environments_if_empty

        inserted = seed_platform_environments_if_empty()
        if inserted:
            logger.info("platform_environments_seeded_on_init", count=inserted)
        from shared.services.agent_content_service import seed_agent_content_if_empty

        agent_inserted = seed_agent_content_if_empty()
        if agent_inserted:
            logger.info("agent_content_seeded_on_init", count=agent_inserted)
    except Exception as e:
        from shared.database.availability import handle_database_error

        handle_database_error("platform_environments_seed_failed", e)
