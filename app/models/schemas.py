"""
Pydantic schemas for API requests/responses
WebSocket message types and REST API models
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field
import uuid


# ============================================================
# WebSocket Message Types
# ============================================================

class WSMessageType(str, Enum):
    """WebSocket message types"""
    # Client -> Server
    CHAT = "chat"
    PING = "ping"
    SWITCH_PROFILE = "switch_profile"

    # Server -> Client
    START = "start"
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"
    WARMUP = "warmup"
    PONG = "pong"
    PROFILE_CHANGED = "profile_changed"
    GPU_UPDATE = "gpu_update"


# ============================================================
# Chat Models
# ============================================================

class ChatMessage(BaseModel):
    """Single chat message"""
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Chat request from client"""
    profile: str = Field(default="qwen", description="Profile ID: qwen or gemma")
    mode: str = Field(default="auto", description="Inference mode: auto, fast, deep")
    messages: list[ChatMessage] = Field(default_factory=list)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    class Config:
        json_schema_extra = {
            "example": {
                "profile": "qwen",
                "mode": "auto",
                "messages": [
                    {"role": "user", "content": "Förklara async/await i Python"}
                ],
                "request_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class ChatStats(BaseModel):
    """Statistics for completed chat response"""
    tokens_generated: int
    tokens_per_second: float
    total_duration_ms: int
    prompt_eval_count: Optional[int] = None
    prompt_eval_duration_ms: Optional[int] = None
    model: str
    profile: str
    provider: str = "ollama"  # ollama or gemini
    mode: str = "auto"  # auto, fast, deep


class TokenChunk(BaseModel):
    """Single token in streaming response"""
    type: Literal["token"] = "token"
    content: str
    request_id: str


class ChatResponse(BaseModel):
    """Complete chat response (non-streaming)"""
    type: Literal["done"] = "done"
    request_id: str
    content: str
    stats: ChatStats


# ============================================================
# WebSocket Protocol Messages
# ============================================================

class WSStartMessage(BaseModel):
    """Sent when chat generation starts"""
    type: Literal["start"] = "start"
    request_id: str
    profile: str
    model: str
    display_name: str  # e.g., "QWEN_NEXUS"


class WSTokenMessage(BaseModel):
    """Single streamed token"""
    type: Literal["token"] = "token"
    content: str
    request_id: str


class WSDoneMessage(BaseModel):
    """Sent when generation completes"""
    type: Literal["done"] = "done"
    request_id: str
    stats: ChatStats


class WSErrorMessage(BaseModel):
    """Error message"""
    type: Literal["error"] = "error"
    request_id: str
    code: str
    message: str
    retry_after_ms: Optional[int] = None


class WSWarmupMessage(BaseModel):
    """Model loading/warmup status"""
    type: Literal["warmup"] = "warmup"
    request_id: str
    status: Literal["loading", "ready", "unloading"]
    model: str
    progress_percent: Optional[int] = None


class WSMessage(BaseModel):
    """Generic WebSocket message wrapper"""
    type: WSMessageType
    request_id: Optional[str] = None
    data: Optional[dict] = None


# ============================================================
# Profile Models
# ============================================================

class ProfileInfo(BaseModel):
    """Profile information for API response"""
    id: str
    name: str
    display_name: str
    description: str
    model: str
    estimated_vram_gb: float
    icon: str
    color: str
    strengths: list[str] = []
    is_active: bool = False
    is_loading: bool = False


class ProfilesResponse(BaseModel):
    """Response for GET /api/profiles"""
    profiles: list[ProfileInfo]
    active_profile: Optional[str] = None
    default_profile: str = "chill"


# ============================================================
# GPU Monitoring Models
# ============================================================

class GPUStats(BaseModel):
    """GPU statistics from nvidia-smi"""
    name: str = "NVIDIA GeForce RTX 4070"
    vram_total_gb: float = 12.0
    vram_used_gb: float = 0.0
    vram_free_gb: float = 12.0
    vram_percent: float = 0.0
    temperature_c: int = 0
    power_draw_w: int = 0
    power_limit_w: int = 200
    gpu_util_percent: int = 0
    memory_util_percent: int = 0
    fan_speed_percent: Optional[int] = None
    is_available: bool = True
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "NVIDIA GeForce RTX 4070",
                "vram_total_gb": 12.0,
                "vram_used_gb": 10.2,
                "vram_free_gb": 1.8,
                "vram_percent": 85.0,
                "temperature_c": 58,
                "power_draw_w": 185,
                "power_limit_w": 200,
                "gpu_util_percent": 95,
                "memory_util_percent": 85,
                "is_available": True
            }
        }


class GPUStatsResponse(BaseModel):
    """Response for GET /api/gpu/stats"""
    gpu: GPUStats
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ollama_models_loaded: list[str] = Field(default_factory=list)


# ============================================================
# Health Check Models
# ============================================================

class OllamaStatus(BaseModel):
    """Ollama service status"""
    connected: bool = False
    version: Optional[str] = None
    models_available: list[str] = Field(default_factory=list)
    models_loaded: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Response for GET /api/health"""
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ollama: OllamaStatus
    gpu_available: bool = False
    checks: dict[str, bool] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": "2025-11-25T17:45:00Z",
                "ollama": {
                    "connected": True,
                    "version": "0.1.0",
                    "models_available": ["qwen3:14b"],
                    "models_loaded": ["qwen3:14b"]
                },
                "gpu_available": True,
                "checks": {
                    "ollama": True,
                    "gpu": True,
                    "think_model": True,
                    "chill_model": True
                }
            }
        }


# ============================================================
# System Info Models
# ============================================================

class SystemInfo(BaseModel):
    """System information for header display"""
    ram_total_gb: float
    ram_used_gb: float
    cpu_percent: float
    cpu_freq_ghz: Optional[float] = None
    uptime_seconds: int


class SystemInfoResponse(BaseModel):
    """Response for GET /api/system/info"""
    system: SystemInfo
    gpu: GPUStats
    timestamp: datetime = Field(default_factory=datetime.utcnow)
