"""Application settings (flat model). Load via shared.config.loader for YAML merge."""

from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Flat settings schema: platform + optional agent overrides + env secrets."""

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
    use_local_data: bool = True
    local_data_path: Optional[str] = None

    vector_retrieval_backend: str = "none"
    faiss_index_path: Optional[str] = None

    default_monthly_budget: float = 500.0
    default_model_name: str = "gpt-4o"
    default_confidence_score: float = 0.85
    recommendation_auto_termination_minutes: int = 0
    recommendation_cost_retry_enabled: bool = True

    guardrail_max_job_id_length: int = 256
    guardrail_max_date_range_days: int = 30
    guardrail_supported_intent: str = "cluster_recommendation"

    admin_usernames: str = "admin"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )


from shared.config.agent_ids import DBX_CLUSTER_TUNING_AGENT_ID

DEFAULT_AGENT_ID = DBX_CLUSTER_TUNING_AGENT_ID


class _SettingsProxy:
    """Module-level `settings` proxy (default agent merged config)."""

    def __getattr__(self, name: str):
        from shared.config.loader import get_agent_settings

        return getattr(get_agent_settings(DEFAULT_AGENT_ID), name)

    def __setattr__(self, name: str, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        from shared.config.loader import get_agent_settings

        setattr(get_agent_settings(DEFAULT_AGENT_ID), name, value)


settings: Settings = _SettingsProxy()  # type: ignore[assignment]
