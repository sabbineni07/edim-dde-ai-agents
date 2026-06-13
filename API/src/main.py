"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from AI.src.core.llm.azure_openai_service import AzureOpenAINotConfiguredError
from API.src.routes import (
    agents,
    chat,
    cost_analytics,
    environment_connections,
    environment_datasets,
    environments,
    health,
    jobs,
    platform,
    recommendations,
    workspace_agents,
    workspace_connections,
)
from shared.config.settings import settings
from shared.guardrails.exceptions import (
    GuardrailValidationError,
    NoJobMetricsError,
    TopicNotSupportedError,
)
from shared.utils.logging import get_logger

logger = get_logger(__name__)


def _register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for domain errors."""

    @app.exception_handler(AzureOpenAINotConfiguredError)
    async def azure_openai_not_configured_handler(
        request: Request, exc: AzureOpenAINotConfiguredError
    ):
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "error_code": "AZURE_OPENAI_NOT_CONFIGURED",
            },
        )

    @app.exception_handler(NoJobMetricsError)
    async def no_job_metrics_handler(request: Request, exc: NoJobMetricsError):
        return JSONResponse(
            status_code=404,
            content={"detail": exc.message, "error_code": exc.error_code},
        )

    @app.exception_handler(TopicNotSupportedError)
    async def topic_not_supported_handler(request: Request, exc: TopicNotSupportedError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "error_code": exc.error_code},
        )

    @app.exception_handler(GuardrailValidationError)
    async def guardrail_validation_handler(request: Request, exc: GuardrailValidationError):
        return JSONResponse(
            status_code=400,
            content={"detail": exc.message, "error_code": exc.error_code},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("application_startup", env=settings.app_env)
    if settings.use_postgres:
        try:
            from shared.database.connection import init_database
            from shared.services.platform_environment_service import (
                seed_platform_environments_if_empty,
            )

            init_database()
            seed_platform_environments_if_empty()
            logger.info("database_initialized")
        except Exception as e:
            logger.warning("database_initialization_failed", error=str(e))
    yield
    logger.info("application_shutdown")


app = FastAPI(
    title="EDIM DDE AI Agents API",
    description="AI-powered cluster configuration recommendations",
    version="1.0.0",
    lifespan=lifespan,
)

_register_exception_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(cost_analytics.router, prefix="/api/cost", tags=["cost-analytics"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(environments.router, prefix="/api/environments", tags=["environments"])
app.include_router(
    environment_connections.router, prefix="/api/environments", tags=["environment-connections"]
)
app.include_router(
    environment_datasets.router, prefix="/api/environments", tags=["environment-datasets"]
)
app.include_router(
    workspace_connections.router, prefix="/api/workspaces", tags=["workspace-connections"]
)
app.include_router(workspace_agents.router, prefix="/api/workspaces", tags=["workspace-agents"])
app.include_router(platform.router, prefix="/api/platform", tags=["platform"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "API.src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development",
    )
