"""
Simons AI Backend - Main Application
FastAPI server for THINK/CHILL dual-model system

Run with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .api.claude_routes import router as claude_router
from .api.constitutional_routes import router as constitutional_router, harvest_websocket
from .api.ocr_routes import router as ocr_router
from .api.Backend_Chat_Stream import websocket_endpoint, cascade_websocket_endpoint, stop_gpu_broadcast, stop_status_pulse
from .api.terminal_ws import terminal_websocket
from .services.ollama_client import ollama_client
from .services.gpu_monitor import gpu_monitor
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

    # Check Ollama connection
    ollama_ok = await ollama_client.is_connected()
    if ollama_ok:
        logger.info("Ollama connection: OK")
        models = await ollama_client.list_models()
        logger.info(f"Available models: {', '.join(models) if models else 'None'}")
    else:
        logger.warning("Ollama connection: FAILED - Start with 'ollama serve'")

    # Check GPU
    gpu_ok = await gpu_monitor.is_gpu_available()
    if gpu_ok:
        stats = await gpu_monitor.get_stats()
        logger.info(f"GPU: {stats.name}")
        logger.info(f"VRAM: {stats.vram_used_gb:.1f}/{stats.vram_total_gb:.1f} GB")
    else:
        logger.warning("GPU monitoring: FAILED - nvidia-smi not available")

    # Optional warmup
    if settings.warmup_on_startup and ollama_ok:
        from .models.Backend_Agent_Prompts import get_profile
        profile = get_profile(settings.warmup_profile)
        logger.info(f"Warming up model: {profile.model}")
        await ollama_client.warmup_model(profile)

    logger.info(f"Server starting on http://{settings.host}:{settings.port}")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down...")
    stop_gpu_broadcast()  # Stop GPU telemetry broadcast
    stop_status_pulse()   # Stop status pulse
    await ollama_client.close()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="Backend for Simons AI - ETERNAL DREAMS chat interface",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST API routes
app.include_router(api_router)
app.include_router(claude_router)
app.include_router(constitutional_router)
app.include_router(ocr_router)

# WebSocket endpoints
app.websocket("/api/chat")(websocket_endpoint)
app.websocket("/api/cascade")(cascade_websocket_endpoint)  # Multi-Agent Cascade: Planner→Coder→Reviewer
app.websocket("/api/terminal")(terminal_websocket)  # Live Preview Workbench: PTY Terminal
app.websocket("/ws/harvest")(harvest_websocket)  # Constitutional AI: Live Harvest Progress


@app.get("/")
async def root():
    """Root endpoint - basic info"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/health",
        "profiles": "/api/profiles",
        "gpu": "/api/gpu/stats",
        "constitutional": "/api/constitutional/health",
        "ocr": "/api/ocr/status",
        "websocket": "ws://localhost:8000/api/chat",
        "cascade": "ws://localhost:8000/api/cascade",
        "terminal": "ws://localhost:8000/api/terminal",
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
