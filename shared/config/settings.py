"""Application settings."""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    azure_subscription_id: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    azure_resource_group: Optional[str] = None

    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_access_token: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    azure_openai_deployment_name: Optional[str] = None
    azure_openai_embedding_deployment: Optional[str] = None

    azure_search_endpoint: Optional[str] = None
    azure_search_api_key: Optional[str] = None
    azure_search_index_name: Optional[str] = None

    postgres_host: Optional[str] = None
    postgres_port: int = 5432
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_database: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("POSTGRES_DATABASE", "POSTGRES_DB"),
    )
    postgres_ssl_mode: str = "prefer"

    azure_sql_server: Optional[str] = None
    azure_sql_database: Optional[str] = None
    azure_sql_username: Optional[str] = None
    azure_sql_password: Optional[str] = None

    use_postgres: bool = True

    azure_storage_account: Optional[str] = None
    azure_storage_key: Optional[str] = None
    azure_storage_container: Optional[str] = None
    azure_key_vault_name: Optional[str] = None

    databricks_server_hostname: Optional[str] = None
    databricks_http_path: Optional[str] = None
    databricks_token: Optional[str] = None
    databricks_job_cluster_metrics_table: Optional[str] = None

    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    use_local_data: bool = False
    local_data_path: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


import warnings
import os

use_env_file = True
if os.path.exists(".env"):
    try:
        with open(".env", "r"):
            pass
    except (PermissionError, IOError):
        use_env_file = False
        warnings.warn("Could not read .env file. Using environment variables only.")

try:
    settings = Settings() if use_env_file else Settings(_env_file=None)
except Exception as e:
    warnings.warn(f"Error loading settings: {e}. Using defaults.")
    settings = Settings(_env_file=None)
