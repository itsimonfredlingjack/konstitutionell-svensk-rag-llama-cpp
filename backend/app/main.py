"""
Constitutional AI Backend - Main Application
FastAPI server for Swedish legal document RAG system

Run with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.constitutional_routes import router as constitutional_router, harvest_websocket
from .services.orchestrator_service import get_orchestrator_service
from .core.error_handlers import register_exception_handlers
from .config import settings
from .utils.logging import setup_logging, get_logger

# Setup logging
setup_logging(
    level=settings.log_level,
    json_output=settings.log_json,
    log_file=settings.log_file,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 60)
    logger.info(f"  {settings.app_name} v{settings.app_version}")
    logger.info("=" * 60)

    # Initialize Constitutional AI Services
    try:
        logger.info("Initializing Constitutional AI Services...")
        orchestrator = get_orchestrator_service()
        await orchestrator.initialize()
        logger.info("✅ Orchestrator & Retrieval Stack ONLINE")
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")

    logger.info(f"Server starting on http://{settings.host}:{settings.port}")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Close Orchestrator services
    try:
        orchestrator = get_orchestrator_service()
        await orchestrator.close()
    except Exception as e:
        logger.error(f"Error closing orchestrator: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Backend for Constitutional AI - Swedish legal document RAG system",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register exception handlers
register_exception_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST API routes
app.include_router(constitutional_router)

# WebSocket endpoints
app.websocket("/ws/harvest")(harvest_websocket)  # Constitutional AI: Live Harvest Progress


@app.get("/")
async def root():
    """Root endpoint - basic info"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "constitutional": "/api/constitutional/health",
        "harvest": "ws://localhost:8000/ws/harvest",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
