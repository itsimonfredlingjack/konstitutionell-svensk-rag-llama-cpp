"""
Application configuration
Environment variables and settings
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


# ═══════════════════════════════════════════════════════════════════════════════
# CENTRAL MODEL CONFIGURATION - PLANNER + GENERALIST
# ═══════════════════════════════════════════════════════════════════════════════

# === MODELS ===
MODEL_PLANNER = "hermes3:8b"            # Hermes3 8B - Tool calling & planering
MODEL_GENERALIST = "gemma3:12b"         # Gemma3 12B - Generalist

# Display names för UI
MODEL_PLANNER_NAME = "PLANNER"
MODEL_GENERALIST_NAME = "GENERALIST"

# Default model
MODEL_DEFAULT = MODEL_GENERALIST

# ═══════════════════════════════════════════════════════════════════════════════
# SAMPLING OPTIMIZATION
# ═══════════════════════════════════════════════════════════════════════════════

# PLANNER (PHI4-reasoning 14B) - 8K context
PLANNER_CONFIG = {
    "num_ctx": 8192,
    "num_predict": 4096,
    "temperature": 0.3,  # Låg temp för precision i planering
    "top_p": 0.9,
    "repeat_penalty": 1.05,
}

# GENERALIST (Gemma3 12B) - 8K context
GENERALIST_CONFIG = {
    "num_ctx": 8192,
    "num_predict": 4096,
    "temperature": 0.7,  # Högre temp för kreativitet
    "top_p": 0.9,
    "repeat_penalty": 1.05,
}
# ═══════════════════════════════════════════════════════════════════════════════


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application
    app_name: str = "Simons AI Backend"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: int = 120

    # Gemini (cloud - FAST mode)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash-exp"

    # Hybrid Orchestrator
    default_mode: str = "auto"  # auto, fast, deep

    # CORS - explicit origins needed when allow_credentials=True
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.86.32:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://192.168.86.32:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://192.168.86.32:5175",
        "http://localhost:3000",      # Constitutional-GPT
        "http://127.0.0.1:3000",
        "http://192.168.86.32:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://192.168.86.32:3001",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.86.32:8000",
    ]
    cors_allow_credentials: bool = True

    # Logging
    log_level: str = "INFO"
    log_json: bool = False
    log_file: Optional[str] = None

    # WebSocket
    ws_heartbeat_interval: int = 30  # seconds
    ws_max_message_size: int = 65536  # bytes

    # Model defaults
    default_profile: str = "chill"
    warmup_on_startup: bool = False
    warmup_profile: str = "chill"

    class Config:
        env_prefix = "LLM_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience exports
settings = get_settings()
