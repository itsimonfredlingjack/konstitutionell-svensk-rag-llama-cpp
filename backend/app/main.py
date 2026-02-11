"""
Constitutional AI Backend - Main Application
FastAPI server for Swedish legal document RAG system

Run with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from slowapi.errors import RateLimitExceeded
from starlette.middleware.gzip import GZipMiddleware

from .api.constitutional_routes import harvest_websocket
from .api.constitutional_routes import router as constitutional_router
from .api.document_routes import router as document_router
from .config import settings
from .core.error_handlers import register_exception_handlers
from .core.rate_limiter import limiter, rate_limit_exceeded_handler
from .middleware import RequestIDMiddleware
from .services.orchestrator_service import get_orchestrator_service
from .utils.logging import get_logger, setup_logging

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

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Request ID middleware for distributed tracing
app.add_middleware(RequestIDMiddleware)

# CORS middleware — restricted methods and headers (was wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
)

# GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include REST API routes
app.include_router(constitutional_router)
app.include_router(document_router)

# WebSocket endpoints
app.websocket("/ws/harvest")(harvest_websocket)  # Constitutional AI: Live Harvest Progress


async def sse_event_stream(request: Request):
    """SSE event stream - MCP compatible with message handling"""
    try:
        # Send initial connection event
        yield ": connected\n\n"

        # Read incoming messages from request body (if POST) or query params
        # For MCP SSE, clients typically send messages via POST to /sse/message
        # But we'll also handle GET for simple connections

        # Send server info as initial event
        server_info = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {"serverInfo": {"name": settings.app_name, "version": settings.app_version}},
        }
        yield f"data: {json.dumps(server_info)}\n\n"

        # Keep connection alive with periodic heartbeats
        while True:
            await asyncio.sleep(30)
            heartbeat = {
                "jsonrpc": "2.0",
                "method": "ping",
                "params": {"timestamp": asyncio.get_event_loop().time()},
            }
            yield f"data: {json.dumps(heartbeat)}\n\n"
    except asyncio.CancelledError:
        # Client disconnected
        pass
    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        error_response = {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}
        yield f"data: {json.dumps(error_response)}\n\n"


@app.get("/sse")
async def sse_endpoint(request: Request):
    """Server-Sent Events endpoint for MCP compatibility"""
    return StreamingResponse(
        sse_event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/sse/message")
async def sse_message_endpoint(request: Request):
    """Handle MCP messages sent via POST (for SSE transport)"""
    try:
        body = await request.json()
        logger.info(f"Received MCP message: {body.get('method', 'unknown')}")

        # Handle initialize request
        if body.get("method") == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": settings.app_name, "version": settings.app_version},
                },
            }
            return response

        # Handle other MCP methods
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32601, "message": f"Method not found: {body.get('method')}"},
        }
    except Exception as e:
        logger.error(f"Error handling MCP message: {e}")
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": str(e)}}


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
