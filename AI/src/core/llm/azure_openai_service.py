"""Azure OpenAI service integration."""

from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings

from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _normalize_azure_endpoint(endpoint: str) -> str:
    """Strip /api/projects/xxx from Foundry URLs - SDK expects base resource URL."""
    if "/api/projects/" in endpoint:
        base = endpoint.split("/api/projects/")[0].rstrip("/")
        logger.info("normalized_foundry_endpoint", original=endpoint[:60], base=base)
        return base
    return endpoint.rstrip("/")


def _build_settings_cached_token_provider():
    """Build a callable that returns an Azure AD token, caching in settings when fetched."""

    def token_provider() -> str:
        token = (settings.azure_openai_access_token or "").strip()
        if not token:
            from shared.auth.azure_tokens import AZURE_OPENAI_AAD_SCOPE, get_azure_access_token

            token = get_azure_access_token(AZURE_OPENAI_AAD_SCOPE)
            settings.azure_openai_access_token = token
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

    def __init__(self):
        """Initialize Azure OpenAI service.

        Raises:
            AzureOpenAINotConfiguredError: When endpoint or credentials are not configured.
        """
        if not settings.azure_openai_endpoint or not settings.azure_openai_endpoint.strip():
            msg = (
                "Azure OpenAI is not configured. Set AZURE_OPENAI_ENDPOINT and use "
                "AZURE_OPENAI_API_KEY, or Azure identity (az login / Managed Identity)."
            )
            logger.error("azure_openai_not_configured", message=msg)
            raise AzureOpenAINotConfiguredError(msg)

        use_api_key = settings.azure_openai_api_key and settings.azure_openai_api_key.strip()
        endpoint = _normalize_azure_endpoint(settings.azure_openai_endpoint)
        api_version = settings.azure_openai_api_version or "2024-05-01-preview"
        deployment = settings.azure_openai_deployment_name or "gpt-4o"
        embedding_deployment = (
            settings.azure_openai_embedding_deployment or "text-embedding-3-small"
        )

        try:
            if use_api_key:
                self.llm = AzureChatOpenAI(
                    azure_endpoint=endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=api_version,
                    azure_deployment=deployment,
                    temperature=0,
                )
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                )
                logger.info("azure_openai_service_initialized", auth="api_key")
            else:
                token_provider = _build_settings_cached_token_provider()
                self.llm = AzureChatOpenAI(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=deployment,
                    azure_ad_token_provider=token_provider,
                    temperature=0,
                )
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                    azure_ad_token_provider=token_provider,
                )
                auth = (
                    "access_token_env"
                    if (settings.azure_openai_access_token or "").strip()
                    else "azure_ad"
                )
                logger.info("azure_openai_service_initialized", auth=auth)
        except Exception as e:
            logger.error("azure_openai_init_failed", error=str(e))
            raise AzureOpenAINotConfiguredError(
                f"Failed to initialize Azure OpenAI: {e}. "
                "Verify AZURE_OPENAI_ENDPOINT, deployment name, and credentials."
            ) from e

    def get_llm(self) -> AzureChatOpenAI:
        """Get the LLM instance."""
        return self.llm

    def get_embeddings(self) -> AzureOpenAIEmbeddings:
        """Get the embeddings model."""
        return self.embeddings
