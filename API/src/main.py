"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.config.settings import settings
from shared.utils.logging import get_logger
from API.src.routes import recommendations, health, cost_analytics

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    logger.info("application_startup", env=settings.app_env)
    if settings.use_postgres:
        try:
            from shared.database.connection import init_database
            init_database()
            logger.info("database_initialized")
        except Exception as e:
            logger.warning("database_initialization_failed", error=str(e))
    yield
    logger.info("application_shutdown")


app = FastAPI(
    title="EDIM DDE AI Agents API",
    description="AI-powered cluster configuration recommendations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(cost_analytics.router, prefix="/api/cost", tags=["cost-analytics"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "API.src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.app_env == "development"
    )

