"""Azure OpenAI service integration."""

from typing import Optional

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from AI.src.core.llm.chat_model_factory import create_azure_chat_model
from shared.config.llm_sampling import ChainKind
from shared.config.settings import Settings, settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_azure_endpoint(endpoint: str) -> str:
    """Strip /api/projects/xxx from Foundry URLs - SDK expects base resource URL."""
    if "/api/projects/" in endpoint:
        base = endpoint.split("/api/projects/")[0].rstrip("/")
        logger.info("normalized_foundry_endpoint", original=endpoint[:60], base=base)
        return base
    return endpoint.rstrip("/")


def _build_settings_cached_token_provider(cfg: Settings):
    """Build a callable that returns an Azure AD token, caching in settings when fetched."""

    def token_provider() -> str:
        token = (cfg.azure_openai_access_token or "").strip()
        if not token:
            from shared.auth.azure_tokens import AZURE_OPENAI_AAD_SCOPE, get_azure_access_token

            token = get_azure_access_token(AZURE_OPENAI_AAD_SCOPE)
            cfg.azure_openai_access_token = token
            logger.debug("azure_openai_token_from_azure_identity", cached=True)
        return token

    return token_provider


class AzureOpenAINotConfiguredError(Exception):
    """Raised when Azure OpenAI is not configured (missing endpoint or credentials)."""


class AzureOpenAIService:
    """Service for Azure OpenAI integration.

    Auth order: (1) API key, (2) cached access token (env or Azure identity), (3) fetch via
    DefaultAzureCredential on first use and store in settings.azure_openai_access_token.
    """

    def __init__(self, config: Optional[Settings] = None):
        """Initialize Azure OpenAI service.

        Raises:
            AzureOpenAINotConfiguredError: When endpoint or credentials are not configured.
        """
        self._cfg = config or settings
        cfg = self._cfg
        if not cfg.azure_openai_endpoint or not cfg.azure_openai_endpoint.strip():
            msg = (
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT and use "
                "AZURE_OPENAI_API_KEY, or Azure identity (az login / Managed Identity)."
            )
            logger.error("azure_openai_not_configured", message=msg)
            raise AzureOpenAINotConfiguredError(msg)

        use_api_key = cfg.azure_openai_api_key and cfg.azure_openai_api_key.strip()
        endpoint = _normalize_azure_endpoint(cfg.azure_openai_endpoint)
        api_version = cfg.azure_openai_api_version or "2024-05-01-preview"
        deployment = cfg.azure_openai_deployment_name or "gpt-4o"
        embedding_deployment = cfg.azure_openai_embedding_deployment or "text-embedding-3-small"

        self._llm_by_chain: dict[str, AzureChatOpenAI] = {}

        try:
            if use_api_key:
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_key=cfg.azure_openai_api_key,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                )
                logger.info("azure_openai_service_initialized", auth="api_key")
            else:
                token_provider = _build_settings_cached_token_provider(cfg)
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                    azure_ad_token_provider=token_provider,
                )
                auth = (
                    "access_token_env"
                    if (cfg.azure_openai_access_token or "").strip()
                    else "azure_ad"
                )
                logger.info("azure_openai_service_initialized", auth=auth)
        except Exception as e:
            logger.error("azure_openai_init_failed", error=str(e))
            raise AzureOpenAINotConfiguredError(
                f"Failed to initialize Azure OpenAI: {e}. "
                "Verify AZURE_OPENAI_ENDPOINT, deployment name, and credentials."
            ) from e

    def get_llm(self, chain: ChainKind = "default") -> AzureChatOpenAI:
        """Get a chat model for the given chain (sizing / explanation / default)."""
        key = chain or "default"
        if key not in self._llm_by_chain:
            self._llm_by_chain[key] = create_azure_chat_model(self._cfg, chain=key)
        return self._llm_by_chain[key]

    def get_embeddings(self) -> AzureOpenAIEmbeddings:
        """Get the embeddings model."""
        return self.embeddings
