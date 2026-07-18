"""Azure AI Foundry LLM service (OpenAI v1 API)."""

from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from AI.src.core.llm.chat_model_factory import create_chat_model
from shared.config.llm_sampling import ChainKind
from shared.config.settings import Settings, settings
from shared.rag.embeddings import embeddings_from_settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _build_settings_cached_token_provider(cfg: Settings):
    """Build a callable that returns an Azure AD token, caching in settings when fetched."""

    def token_provider() -> str:
        token = (cfg.azure_openai_access_token or "").strip()
        if not token:
            from shared.auth.foundry_tokens import get_foundry_access_token

            token = get_foundry_access_token(cfg)
            cfg.azure_openai_access_token = token
            logger.debug("foundry_llm_token_from_azure_identity", cached=True)
        return token

    return token_provider


class FoundryLLMNotConfiguredError(Exception):
    """Raised when Foundry LLM is not configured (missing endpoint or credentials)."""


class FoundryLLMService:
    """Service for Azure AI Foundry chat and embedding models (OpenAI v1 route).

    Auth order: (1) API key, (2) cached access token (env or Azure identity), (3) fetch via
    DefaultAzureCredential on first use and store in settings.azure_openai_access_token.
    """

    def __init__(self, config: Optional[Settings] = None):
        """Initialize Foundry LLM service.

        Raises:
            FoundryLLMNotConfiguredError: When endpoint or credentials are not configured.
        """
        self._cfg = config or settings
        cfg = self._cfg
        if not cfg.azure_openai_endpoint or not cfg.azure_openai_endpoint.strip():
            msg = (
                "Azure AI Foundry LLM is not configured. Set AZURE_OPENAI_ENDPOINT and use "
                "AZURE_OPENAI_API_KEY, or Azure identity (az login / Managed Identity)."
            )
            logger.error("foundry_llm_not_configured", message=msg)
            raise FoundryLLMNotConfiguredError(msg)

        use_api_key = cfg.azure_openai_api_key and cfg.azure_openai_api_key.strip()
        self._llm_by_chain: dict[str, BaseChatModel] = {}

        try:
            self.embeddings: Embeddings = embeddings_from_settings(cfg)
            auth = (
                "api_key"
                if use_api_key
                else (
                    "access_token_env"
                    if (cfg.azure_openai_access_token or "").strip()
                    else "azure_ad"
                )
            )
            logger.info("foundry_llm_service_initialized", auth=auth)
        except Exception as e:
            logger.error("foundry_llm_init_failed", error=str(e))
            raise FoundryLLMNotConfiguredError(
                f"Failed to initialize Foundry LLM: {e}. "
                "Verify AZURE_OPENAI_ENDPOINT, deployment name, and credentials."
            ) from e

    def get_llm(self, chain: ChainKind = "default") -> BaseChatModel:
        """Get a chat model for the given chain (sizing / explanation / default)."""
        key = chain or "default"
        if key not in self._llm_by_chain:
            self._llm_by_chain[key] = create_chat_model(self._cfg, chain=key)
        return self._llm_by_chain[key]

    def get_embeddings(self) -> Embeddings:
        """Get the embeddings model."""
        return self.embeddings
