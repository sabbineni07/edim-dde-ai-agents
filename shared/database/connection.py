"""Database connection management."""

from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def get_database_url() -> str:
    if settings.use_postgres:
        host = settings.postgres_host or "localhost"
        port = settings.postgres_port
        user = settings.postgres_user or "postgres"
        password = settings.postgres_password or "postgres"
        database = settings.postgres_database or "ai_agents"
        ssl_mode = settings.postgres_ssl_mode
        if ssl_mode == "disable":
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return f"postgresql://{user}:{password}@{host}:{port}/{database}?sslmode={ssl_mode}"
    else:
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
        else:
            _engine = create_engine(
                database_url, poolclass=NullPool, echo=settings.app_env == "development"
            )
        logger.info(
            "database_engine_created",
            database_type="postgresql" if settings.use_postgres else "sqlserver",
        )
    return _engine


def get_database_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_database_engine()
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionLocal()


def init_database():
    from shared.database.models import Base

    engine = get_database_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("database_tables_initialized")
