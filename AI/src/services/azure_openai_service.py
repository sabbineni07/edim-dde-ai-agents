"""Azure OpenAI service integration."""
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from shared.config.settings import settings
from shared.utils.logging import get_logger

logger = get_logger(__name__)

# Scope for Azure OpenAI / Cognitive Services when using Azure AD
_AZURE_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"


def _normalize_azure_endpoint(endpoint: str) -> str:
    """Strip /api/projects/xxx from Foundry URLs - SDK expects base resource URL."""
    if "/api/projects/" in endpoint:
        base = endpoint.split("/api/projects/")[0].rstrip("/")
        logger.info("normalized_foundry_endpoint", original=endpoint[:60], base=base)
        return base
    return endpoint.rstrip("/")


def _build_azure_ad_token_provider():
    """Build a callable that returns an Azure AD token (for Managed Identity / az login)."""
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    def token_provider():
        token = credential.get_token(_AZURE_OPENAI_SCOPE)
        return token.token
    return token_provider


def _build_env_token_provider(token: str):
    """Build a callable that returns the given token (e.g. from AZURE_OPENAI_ACCESS_TOKEN). No refresh."""
    def token_provider():
        return token
    return token_provider


class AzureOpenAIService:
    """Service for Azure OpenAI integration.
    Auth order: (1) API key, (2) token from env AZURE_OPENAI_ACCESS_TOKEN, (3) DefaultAzureCredential.
    """
    
    def __init__(self):
        """Initialize Azure OpenAI service."""
        if not settings.azure_openai_endpoint:
            logger.warning("azure_openai_credentials_missing_using_mock")
            from AI.src.services.mock_llm_service import MockLLMService
            mock_service = MockLLMService()
            self.llm = mock_service.get_llm()
            self.embeddings = mock_service.get_embeddings()
            return
        
        use_api_key = settings.azure_openai_api_key and settings.azure_openai_api_key.strip()
        use_token_env = settings.azure_openai_access_token and settings.azure_openai_access_token.strip()
        endpoint = _normalize_azure_endpoint(settings.azure_openai_endpoint)
        api_version = settings.azure_openai_api_version or "2024-05-01-preview"
        deployment = settings.azure_openai_deployment_name or "gpt-4o"
        embedding_deployment = settings.azure_openai_embedding_deployment or "text-embedding-3-small"

        try:
            if use_api_key:
                self.llm = AzureChatOpenAI(
                    azure_endpoint=endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=api_version,
                    azure_deployment=deployment,
                    temperature=0.7,
                )
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                )
                logger.info("azure_openai_service_initialized", auth="api_key")
            elif use_token_env:
                token_provider = _build_env_token_provider(settings.azure_openai_access_token)
                self.llm = AzureChatOpenAI(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=deployment,
                    azure_ad_token_provider=token_provider,
                    temperature=0.7,
                )
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                    azure_ad_token_provider=token_provider,
                )
                logger.info("azure_openai_service_initialized", auth="access_token_env")
            else:
                token_provider = _build_azure_ad_token_provider()
                self.llm = AzureChatOpenAI(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=deployment,
                    azure_ad_token_provider=token_provider,
                    temperature=0.7,
                )
                self.embeddings = AzureOpenAIEmbeddings(
                    azure_endpoint=endpoint,
                    api_version=api_version,
                    azure_deployment=embedding_deployment,
                    azure_ad_token_provider=token_provider,
                )
                logger.info("azure_openai_service_initialized", auth="azure_ad")
        except Exception as e:
            logger.warning(f"azure_openai_init_failed_using_mock: {e}")
            from AI.src.services.mock_llm_service import MockLLMService
            mock_service = MockLLMService()
            self.llm = mock_service.get_llm()
            self.embeddings = mock_service.get_embeddings()
    
    def get_llm(self) -> AzureChatOpenAI:
        """Get the LLM instance."""
        return self.llm
    
    def get_embeddings(self) -> AzureOpenAIEmbeddings:
        """Get the embeddings model."""
        return self.embeddings

