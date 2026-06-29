"""Database connection management."""

from __future__ import annotations

import time
from typing import Any, Optional
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


def _databricks_workspace_host() -> Optional[str]:
    host = (settings.databricks_host or "").strip()
    if host:
        return host if host.startswith("http") else f"https://{host}"
    server_hostname = (settings.databricks_server_hostname or "").strip()
    if server_hostname:
        return f"https://{server_hostname}"
    return None


def _get_workspace_client():
    from databricks.sdk import WorkspaceClient

    kwargs: dict[str, Any] = {}
    host = _databricks_workspace_host()
    if host:
        kwargs["host"] = host
    client_id = (settings.databricks_client_id or "").strip()
    client_secret = (settings.databricks_client_secret or "").strip()
    if client_id and client_secret:
        kwargs["client_id"] = client_id
        kwargs["client_secret"] = client_secret
    return WorkspaceClient(**kwargs)


def _refresh_oauth_token() -> str:
    global _oauth_token, _oauth_token_expiry

    if _oauth_token is not None and time.time() < _oauth_token_expiry - 120:
        return _oauth_token

    endpoint = settings.postgres_lakebase_endpoint
    if not endpoint:
        raise ValueError("POSTGRES_LAKEBASE_ENDPOINT is required for Lakebase OAuth")

    client = _get_workspace_client()
    credential = client.postgres.generate_database_credential(endpoint=endpoint)
    _oauth_token = credential.token
    expire_time = credential.expire_time
    if expire_time is None:
        _oauth_token_expiry = time.time() + 3600
    elif hasattr(expire_time, "timestamp"):
        _oauth_token_expiry = float(expire_time.timestamp())
    elif hasattr(expire_time, "seconds"):
        _oauth_token_expiry = float(expire_time.seconds)
    else:
        _oauth_token_expiry = time.time() + 3600
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


def init_database():
    from shared.database.models import Base

    engine = get_database_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("database_tables_initialized")
    try:
        from shared.services.platform_environment_service import seed_platform_environments_if_empty

        inserted = seed_platform_environments_if_empty()
        if inserted:
            logger.info("platform_environments_seeded_on_init", count=inserted)
    except Exception as e:
        from shared.database.availability import handle_database_error

        handle_database_error("platform_environments_seed_failed", e)
