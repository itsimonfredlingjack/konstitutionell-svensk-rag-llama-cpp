"""
NERVE CENTER Backend API
Real-time system monitoring for AI server infrastructure
"""

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment variables from .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Service URLs (configurable via environment variables)
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
CONSTITUTIONAL_API_URL: str = os.getenv("CONSTITUTIONAL_API_URL", "http://localhost:8000")
QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
API_PORT: int = int(os.getenv("API_PORT", "3003"))

# Path to frontend dist
FRONTEND_DIST = Path(__file__).parent.parent / "dist"


# ============================================================================
# Models
# ============================================================================


class GpuProcess(BaseModel):
    pid: int
    name: str
    memory: int  # MiB


class GpuStats(BaseModel):
    name: str
    temperature: float
    utilization: float
    memory_used: float  # MiB
    memory_total: float  # MiB
    power: float  # Watts
    processes: list[GpuProcess]


class ServiceStatus(BaseModel):
    name: str
    type: str  # systemd, docker, port
    status: str  # running, stopped, error, unhealthy
    port: Optional[int] = None
    pid: Optional[int] = None
    uptime: Optional[int] = None  # seconds


class OllamaModel(BaseModel):
    name: str
    size: int  # bytes
    loaded: bool
    vram: Optional[int] = None  # MiB


class OllamaStatus(BaseModel):
    models: list[OllamaModel]
    running: Optional[str] = None


class SystemMetrics(BaseModel):
    timestamp: int
    gpu: GpuStats
    services: list[ServiceStatus]
    ollama: OllamaStatus


# ============================================================================
# Agent Loop Models (Constitutional AI Pipeline)
# ============================================================================


class ComponentHealth(BaseModel):
    """Health status for a single component."""

    name: str
    status: str  # "ok", "degraded", "error", "offline"
    latency_ms: Optional[int] = None
    message: Optional[str] = None
    last_check: int  # timestamp ms


class ModelStatus(BaseModel):
    """Status of an AI model."""

    name: str
    loaded: bool
    responsive: bool
    latency_ms: Optional[int] = None


class AgentLoopStatus(BaseModel):
    """Complete agent loop pipeline status."""

    timestamp: int
    overall_status: str  # "healthy", "degraded", "critical"

    # Pipeline stages
    chat: ComponentHealth  # Input layer
    assist: ComponentHealth  # LLM generation
    evidence: ComponentHealth  # RAG/Qdrant retrieval
    guardian: ComponentHealth  # Jail warden verification

    # Core services
    ollama: ComponentHealth
    qdrant: ComponentHealth

    # Models
    models: list[ModelStatus]
    active_model: Optional[str] = None

    # Recent activity (last 5 events)
    recent_events: list[dict] = []


# ============================================================================
# System Commands
# ============================================================================


async def run_command(cmd: list[str], timeout: float = 5.0) -> tuple[str, str, int]:
    """Run a shell command asynchronously."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(), stderr.decode(), proc.returncode or 0
    except asyncio.TimeoutError:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


async def get_gpu_stats() -> GpuStats:
    """Get NVIDIA GPU stats using nvidia-smi."""
    # Get basic GPU info
    stdout, stderr, rc = await run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
            "--format=csv,noheader,nounits",
        ]
    )

    if rc != 0:
        return GpuStats(
            name="GPU Error",
            temperature=0,
            utilization=0,
            memory_used=0,
            memory_total=0,
            power=0,
            processes=[],
        )

    parts = [p.strip() for p in stdout.strip().split(",")]
    name = parts[0] if len(parts) > 0 else "Unknown GPU"
    temp = float(parts[1]) if len(parts) > 1 else 0
    util = float(parts[2]) if len(parts) > 2 else 0
    mem_used = float(parts[3]) if len(parts) > 3 else 0
    mem_total = float(parts[4]) if len(parts) > 4 else 0
    power = float(parts[5]) if len(parts) > 5 else 0

    # Get GPU processes
    proc_stdout, _, proc_rc = await run_command(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]
    )

    processes = []
    if proc_rc == 0 and proc_stdout.strip():
        for line in proc_stdout.strip().split("\n"):
            if line.strip():
                proc_parts = [p.strip() for p in line.split(",")]
                if len(proc_parts) >= 3:
                    try:
                        processes.append(
                            GpuProcess(
                                pid=int(proc_parts[0]),
                                name=proc_parts[1].split("/")[-1],  # Just filename
                                memory=int(proc_parts[2]),
                            )
                        )
                    except (ValueError, IndexError):
                        pass

    return GpuStats(
        name=name,
        temperature=temp,
        utilization=util,
        memory_used=mem_used,
        memory_total=mem_total,
        power=power,
        processes=processes,
    )


async def get_service_status(
    name: str, service_type: str, port: Optional[int] = None
) -> ServiceStatus:
    """Get status of a service."""

    if service_type == "systemd":
        stdout, _, rc = await run_command(["systemctl", "is-active", name])
        status = "running" if stdout.strip() == "active" else "stopped"

        # Get uptime if running
        uptime = None
        if status == "running":
            prop_stdout, _, _ = await run_command(
                ["systemctl", "show", name, "--property=ActiveEnterTimestamp"]
            )
            if "=" in prop_stdout:
                timestamp_str = prop_stdout.split("=")[1].strip()
                if timestamp_str:
                    try:
                        # Parse systemd timestamp
                        from dateutil.parser import parse

                        start_time = parse(timestamp_str)
                        uptime = int((datetime.now(start_time.tzinfo) - start_time).total_seconds())
                    except:
                        pass

        return ServiceStatus(name=name, type=service_type, status=status, port=port, uptime=uptime)

    elif service_type == "docker":
        stdout, _, rc = await run_command(
            ["docker", "inspect", "--format", "{{.State.Status}}:{{.State.Health.Status}}", name]
        )
        if rc != 0:
            return ServiceStatus(name=name, type=service_type, status="stopped", port=port)

        parts = stdout.strip().split(":")
        container_status = parts[0] if parts else "unknown"
        health_status = parts[1] if len(parts) > 1 else ""

        if container_status == "running":
            if health_status == "unhealthy":
                status = "unhealthy"
            else:
                status = "running"
        else:
            status = "stopped"

        return ServiceStatus(name=name, type=service_type, status=status, port=port)

    elif service_type == "port":
        stdout, _, rc = await run_command(["lsof", "-i", f":{port}", "-t"])
        if rc == 0 and stdout.strip():
            pid = int(stdout.strip().split("\n")[0])
            return ServiceStatus(name=name, type=service_type, status="running", port=port, pid=pid)
        return ServiceStatus(name=name, type=service_type, status="stopped", port=port)

    return ServiceStatus(name=name, type=service_type, status="error", port=port)


async def get_all_services() -> list[ServiceStatus]:
    """Get status of all monitored services."""
    services_config = [
        ("ollama", "systemd", 11434),
        ("nginx", "systemd", 80),
        ("docker", "systemd", None),
        ("second-brain-qdrant", "docker", 6333),  # Actual container name
        ("second-brain-postgres", "docker", 5434),  # Actual container name
        ("uvicorn", "port", 8000),
        ("vite-5173", "port", 5173),
        ("vite-5174", "port", 5174),
        ("viking-dashboard", "port", 8081),
        ("nerve-center", "port", 3003),
    ]

    tasks = [get_service_status(name, stype, port) for name, stype, port in services_config]

    return await asyncio.gather(*tasks)


def parse_size_string(size_str: str) -> int:
    """Parse size string like '14 GB' or '274 MB' to bytes."""
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|B)", size_str, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        unit = match.group(2).upper()
        if unit == "GB":
            return int(value * 1_000_000_000)
        elif unit == "MB":
            return int(value * 1_000_000)
        elif unit == "KB":
            return int(value * 1_000)
        return int(value)
    return 0


def parse_size_to_mib(size_str: str) -> int:
    """Parse size string like '14 GB' to MiB."""
    match = re.match(r"([\d.]+)\s*(GB|MB|KB|B)", size_str, re.IGNORECASE)
    if match:
        value = float(match.group(1))
        unit = match.group(2).upper()
        if unit == "GB":
            return int(value * 1024)  # GB to MiB
        elif unit == "MB":
            return int(value)  # Already MiB (close enough)
        elif unit == "KB":
            return int(value / 1024)
        return int(value / (1024 * 1024))
    return 0


async def get_ollama_status() -> OllamaStatus:
    """Get Ollama models and running status."""
    # Get all models via `ollama list`
    # Format: NAME    ID    SIZE    MODIFIED
    # Example: gpt-oss:20b    17052f91a42e    13 GB    40 hours ago
    stdout, _, rc = await run_command(["ollama", "list"])
    models = []

    if rc == 0:
        lines = stdout.strip().split("\n")
        for line in lines[1:]:  # Skip header
            if line.strip():
                # Split by 2+ whitespace to handle variable-width columns
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) >= 3:
                    name = parts[0]
                    size = parse_size_string(parts[2])
                    models.append(OllamaModel(name=name, size=size, loaded=False))

    # Get running model via `ollama ps`
    # Format: NAME    ID    SIZE    PROCESSOR    CONTEXT    UNTIL
    # Example: gptoss-agent:latest    e57fe9f327a4    14 GB    23%/77% CPU/GPU    4096    4 minutes from now
    ps_stdout, _, ps_rc = await run_command(["ollama", "ps"])
    running = None

    if ps_rc == 0:
        lines = ps_stdout.strip().split("\n")
        for line in lines[1:]:  # Skip header
            if line.strip():
                # Split by 2+ whitespace
                parts = re.split(r"\s{2,}", line.strip())
                if parts:
                    running = parts[0]
                    vram_mib = parse_size_to_mib(parts[2]) if len(parts) > 2 else None

                    # Mark as loaded and set VRAM
                    found = False
                    for model in models:
                        if model.name == running:
                            model.loaded = True
                            model.vram = vram_mib
                            found = True
                            break

                    # If running model not in list (alias/different name), add it
                    if not found:
                        models.append(
                            OllamaModel(
                                name=running,
                                size=parse_size_string(parts[2]) if len(parts) > 2 else 0,
                                loaded=True,
                                vram=vram_mib,
                            )
                        )
                    break

    return OllamaStatus(models=models, running=running)


async def get_system_metrics() -> SystemMetrics:
    """Get all system metrics."""
    gpu, services, ollama = await asyncio.gather(
        get_gpu_stats(), get_all_services(), get_ollama_status()
    )

    return SystemMetrics(
        timestamp=int(datetime.now().timestamp() * 1000), gpu=gpu, services=services, ollama=ollama
    )


# ============================================================================
# Agent Loop Health Checks
# ============================================================================

import aiohttp

# Required models for Constitutional AI
REQUIRED_MODELS = ["ministral-3:14b", "nomic-embed-text:latest"]
VOICE_MODELS = ["fcole90/ai-sweden-gpt-sw3:6.7b", "gpt-sw3:6.7b"]  # Optional


async def check_ollama_health() -> tuple[ComponentHealth, list[ModelStatus], Optional[str]]:
    """Check Ollama service and model availability."""
    now = int(datetime.now().timestamp() * 1000)
    models_status = []
    active_model = None

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            start = datetime.now()
            async with session.get(f"{OLLAMA_URL}/api/tags") as resp:
                latency = int((datetime.now() - start).total_seconds() * 1000)

                if resp.status != 200:
                    return (
                        ComponentHealth(
                            name="ollama",
                            status="error",
                            latency_ms=latency,
                            message=f"HTTP {resp.status}",
                            last_check=now,
                        ),
                        [],
                        None,
                    )

                data = await resp.json()
                available_models = {m["name"] for m in data.get("models", [])}

                # Check required models
                for model_name in REQUIRED_MODELS:
                    loaded = model_name in available_models
                    models_status.append(
                        ModelStatus(
                            name=model_name,
                            loaded=loaded,
                            responsive=loaded,
                            latency_ms=latency if loaded else None,
                        )
                    )

                # Check voice models (optional)
                for model_name in VOICE_MODELS:
                    if model_name in available_models:
                        models_status.append(
                            ModelStatus(
                                name=model_name, loaded=True, responsive=True, latency_ms=latency
                            )
                        )
                        break

            # Check what's running
            async with session.get(f"{OLLAMA_URL}/api/ps") as ps_resp:
                if ps_resp.status == 200:
                    ps_data = await ps_resp.json()
                    running_models = ps_data.get("models", [])
                    if running_models:
                        active_model = running_models[0].get("name")
                        # Update model status
                        for ms in models_status:
                            if ms.name == active_model:
                                ms.responsive = True

                return (
                    ComponentHealth(
                        name="ollama",
                        status="ok",
                        latency_ms=latency,
                        message=f"{len(available_models)} models available",
                        last_check=now,
                    ),
                    models_status,
                    active_model,
                )

    except asyncio.TimeoutError:
        logger.warning(f"Ollama health check timeout: {OLLAMA_URL}")
        return (
            ComponentHealth(
                name="ollama", status="offline", message="Connection timeout", last_check=now
            ),
            [],
            None,
        )
    except aiohttp.ClientError as e:
        logger.error(f"Ollama health check client error: {e}")
        return (
            ComponentHealth(
                name="ollama",
                status="error",
                message=f"Connection error: {str(e)[:80]}",
                last_check=now,
            ),
            [],
            None,
        )
    except Exception as e:
        logger.exception(f"Unexpected error in Ollama health check: {e}")
        return (
            ComponentHealth(
                name="ollama",
                status="error",
                message=f"Unexpected error: {str(e)[:80]}",
                last_check=now,
            ),
            [],
            None,
        )


async def check_qdrant_health() -> ComponentHealth:
    """Check Qdrant vector database health."""
    now = int(datetime.now().timestamp() * 1000)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
            start = datetime.now()
            async with session.get(f"{QDRANT_URL}/health") as resp:
                latency = int((datetime.now() - start).total_seconds() * 1000)

                if resp.status == 200:
                    return ComponentHealth(
                        name="qdrant",
                        status="ok",
                        latency_ms=latency,
                        message="Second Brain online",
                        last_check=now,
                    )
                else:
                    return ComponentHealth(
                        name="qdrant",
                        status="error",
                        latency_ms=latency,
                        message=f"HTTP {resp.status}",
                        last_check=now,
                    )
    except asyncio.TimeoutError:
        logger.warning(f"Qdrant health check timeout: {QDRANT_URL}")
        return ComponentHealth(
            name="qdrant", status="offline", message="Connection timeout", last_check=now
        )
    except aiohttp.ClientError as e:
        logger.error(f"Qdrant health check client error: {e}")
        return ComponentHealth(
            name="qdrant",
            status="offline",
            message=f"Connection error: {str(e)[:80]}",
            last_check=now,
        )
    except Exception as e:
        logger.exception(f"Unexpected error in Qdrant health check: {e}")
        return ComponentHealth(
            name="qdrant",
            status="offline",
            message=f"Unexpected error: {str(e)[:80]}",
            last_check=now,
        )


async def check_constitutional_api() -> (
    tuple[ComponentHealth, ComponentHealth, ComponentHealth, ComponentHealth]
):
    """Check Constitutional AI API endpoints for pipeline health."""
    now = int(datetime.now().timestamp() * 1000)

    # Default offline states
    chat_health = ComponentHealth(
        name="chat", status="offline", message="API unreachable", last_check=now
    )
    assist_health = ComponentHealth(
        name="assist", status="offline", message="API unreachable", last_check=now
    )
    evidence_health = ComponentHealth(
        name="evidence", status="offline", message="API unreachable", last_check=now
    )
    guardian_health = ComponentHealth(
        name="guardian", status="offline", message="API unreachable", last_check=now
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            # Check if API is up at all
            start = datetime.now()
            async with session.get(f"{CONSTITUTIONAL_API_URL}/health") as resp:
                latency = int((datetime.now() - start).total_seconds() * 1000)

                if resp.status == 200:
                    # API is up, assume pipeline stages are available
                    chat_health = ComponentHealth(
                        name="chat",
                        status="ok",
                        latency_ms=latency,
                        message="Ready for input",
                        last_check=now,
                    )
                    assist_health = ComponentHealth(
                        name="assist",
                        status="ok",
                        latency_ms=latency,
                        message="LLM ready",
                        last_check=now,
                    )
                    evidence_health = ComponentHealth(
                        name="evidence",
                        status="ok",
                        latency_ms=latency,
                        message="RAG pipeline ready",
                        last_check=now,
                    )
                    guardian_health = ComponentHealth(
                        name="guardian",
                        status="ok",
                        latency_ms=latency,
                        message="Jail Warden active",
                        last_check=now,
                    )
                elif resp.status == 404:
                    # API up but no /health endpoint - still good
                    chat_health = ComponentHealth(
                        name="chat",
                        status="ok",
                        latency_ms=latency,
                        message="API online",
                        last_check=now,
                    )
                    assist_health = ComponentHealth(
                        name="assist",
                        status="ok",
                        latency_ms=latency,
                        message="API online",
                        last_check=now,
                    )
                    evidence_health = ComponentHealth(
                        name="evidence",
                        status="ok",
                        latency_ms=latency,
                        message="API online",
                        last_check=now,
                    )
                    guardian_health = ComponentHealth(
                        name="guardian",
                        status="ok",
                        latency_ms=latency,
                        message="API online",
                        last_check=now,
                    )

    except asyncio.TimeoutError:
        logger.warning(f"Constitutional API health check timeout: {CONSTITUTIONAL_API_URL}")
        # Keep defaults (offline states)
    except aiohttp.ClientConnectorError as e:
        logger.debug(f"Constitutional API connection error, checking if port is open: {e}")
        # Try alternative - check if port is open
        try:
            port = CONSTITUTIONAL_API_URL.split(":")[-1].split("/")[0]
            stdout, _, rc = await run_command(["lsof", "-i", f":{port}", "-t"])
            if rc == 0 and stdout.strip():
                logger.info(f"Constitutional API port {port} is open but not responding")
                chat_health = ComponentHealth(
                    name="chat",
                    status="degraded",
                    message="API running but not responding",
                    last_check=now,
                )
                assist_health = ComponentHealth(
                    name="assist",
                    status="degraded",
                    message="API running but not responding",
                    last_check=now,
                )
                evidence_health = ComponentHealth(
                    name="evidence",
                    status="degraded",
                    message="API running but not responding",
                    last_check=now,
                )
                guardian_health = ComponentHealth(
                    name="guardian",
                    status="degraded",
                    message="API running but not responding",
                    last_check=now,
                )
        except Exception as port_check_error:
            logger.debug(f"Port check failed: {port_check_error}")
            # Keep defaults
    except aiohttp.ClientError as e:
        logger.error(f"Constitutional API health check client error: {e}")
        # Keep defaults (offline states)
    except Exception as e:
        logger.exception(f"Unexpected error in Constitutional API health check: {e}")
        # Keep defaults (offline states)

    return chat_health, assist_health, evidence_health, guardian_health


async def get_agent_loop_status() -> AgentLoopStatus:
    """Get complete agent loop pipeline status."""
    now = int(datetime.now().timestamp() * 1000)

    # Run all health checks in parallel
    (
        (ollama_health, models, active_model),
        qdrant_health,
        (chat, assist, evidence, guardian),
    ) = await asyncio.gather(
        check_ollama_health(), check_qdrant_health(), check_constitutional_api()
    )

    # Determine overall status
    all_components = [chat, assist, evidence, guardian, ollama_health, qdrant_health]

    critical_count = sum(1 for c in all_components if c.status in ("offline", "error"))
    degraded_count = sum(1 for c in all_components if c.status == "degraded")

    if critical_count >= 2:
        overall = "critical"
    elif critical_count == 1 or degraded_count >= 2:
        overall = "degraded"
    else:
        overall = "healthy"

    # If Qdrant is down, evidence layer is degraded
    if qdrant_health.status in ("offline", "error"):
        evidence = ComponentHealth(
            name="evidence", status="error", message="Qdrant offline - no RAG", last_check=now
        )

    # If no models loaded, assist is degraded
    brain_model_ok = any(m.loaded for m in models if "ministral" in m.name.lower())
    if not brain_model_ok:
        assist = ComponentHealth(
            name="assist", status="error", message="BRAIN model not available", last_check=now
        )

    return AgentLoopStatus(
        timestamp=now,
        overall_status=overall,
        chat=chat,
        assist=assist,
        evidence=evidence,
        guardian=guardian,
        ollama=ollama_health,
        qdrant=qdrant_health,
        models=models,
        active_model=active_model,
        recent_events=[],  # TODO: Add event logging
    )


# ============================================================================
# FastAPI App
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan events."""
    logger.info("🚀 NERVE CENTER API starting...")
    logger.info(
        f"Configuration: OLLAMA_URL={OLLAMA_URL}, QDRANT_URL={QDRANT_URL}, CONSTITUTIONAL_API_URL={CONSTITUTIONAL_API_URL}, API_PORT={API_PORT}"
    )
    yield
    logger.info("👋 NERVE CENTER API shutting down...")


app = FastAPI(
    title="NERVE CENTER API",
    description="Real-time system monitoring for AI server infrastructure",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Serve frontend index.html or API status."""
    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "ok", "service": "nerve-center-api", "version": "1.0.0"}


@app.get("/api/metrics", response_model=SystemMetrics)
async def get_metrics():
    """Get current system metrics."""
    return await get_system_metrics()


@app.get("/api/gpu", response_model=GpuStats)
async def get_gpu():
    """Get GPU stats only."""
    return await get_gpu_stats()


@app.get("/api/services", response_model=list[ServiceStatus])
async def get_services():
    """Get all service statuses."""
    return await get_all_services()


@app.get("/api/ollama", response_model=OllamaStatus)
async def get_ollama():
    """Get Ollama status."""
    return await get_ollama_status()


@app.get("/api/agent-loop", response_model=AgentLoopStatus)
async def get_agent_loop():
    """Get Constitutional AI agent loop pipeline status."""
    return await get_agent_loop_status()


@app.post("/api/ollama/load/{model_name}")
async def load_ollama_model(model_name: str):
    """Load an Ollama model."""
    # Use a simple prompt to load the model
    stdout, stderr, rc = await run_command(["ollama", "run", model_name, "hello"], timeout=120.0)
    if rc == 0:
        return {"status": "ok", "model": model_name, "loaded": True}
    return {"status": "error", "model": model_name, "error": stderr}


@app.post("/api/ollama/unload")
async def unload_ollama_model():
    """Unload current Ollama model (stop ollama serve and restart)."""
    # This is tricky - Ollama doesn't have an explicit unload
    # For now, just report what's running
    status = await get_ollama_status()
    return {"status": "ok", "running": status.running, "note": "Manual unload not supported"}


@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics updates."""
    await websocket.accept()
    try:
        while True:
            metrics = await get_system_metrics()
            await websocket.send_json(metrics.model_dump())
            await asyncio.sleep(2)  # Send updates every 2 seconds
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")


# Mount static files for frontend assets (must be after API routes)
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    # Catch-all for SPA routing - serve index.html for non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for any non-API route."""
        # Don't intercept API routes or WebSocket
        if full_path.startswith(("api/", "ws/")):
            return {"error": "not found"}
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"error": "frontend not built"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
