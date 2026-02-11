"""
Application configuration for Constitutional AI Backend
Environment variables and settings
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # Application
    app_name: str = "Constitutional AI Backend"
    app_version: str = "2.0.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8900

    # LLM (llama-server, OpenAI-compatible)
    llm_base_url: str = "http://localhost:8080/v1"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: int = 120

    # CRAG (Corrective RAG) Settings
    # Maps to CONST_CRAG_ENABLED and CONST_CRAG_ENABLE_SELF_REFLECTION
    crag_enabled: bool = False
    crag_enable_self_reflection: bool = False
    crag_grade_threshold: float = 0.15

    # Backwards compatibility for typo "CAG" (Maps to CONST_CAG_...)
    cag_enabled: bool = False
    cag_enable_self_reflection: bool = False

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
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.86.32:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://192.168.86.32:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://192.168.86.32:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
        "http://192.168.86.32:3003",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://192.168.86.32:8000",
        "https://swerag.fredlingautomation.dev",
        "https://swerag-api.fredlingautomation.dev",
    ]
    cors_allow_credentials: bool = True

    # Logging
    log_level: str = "INFO"
    log_json: bool = False
    log_file: Optional[str] = None

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_max_message_size: int = 65536

    model_config = {
        "env_prefix": "CONST_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience exports
settings = get_settings()
