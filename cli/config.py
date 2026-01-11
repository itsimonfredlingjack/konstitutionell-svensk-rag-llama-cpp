"""
Configuration for Simons AI CLI
Centralized settings and reconnect logic
"""

import os

# Import central model config from backend
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from app.config import (
        MODEL_ARCHITECT,
        MODEL_ARCHITECT_DESC,
        MODEL_ARCHITECT_NAME,
        MODEL_CODER,
        MODEL_CODER_DESC,
        MODEL_CODER_NAME,
    )
except ImportError:
    # Fallback if not running from project root
    MODEL_ARCHITECT = "gpt-oss"
    MODEL_CODER = "devstral:24b"
    MODEL_ARCHITECT_NAME = "GPT-OSS 20B"
    MODEL_CODER_NAME = "Devstral 24B"
    MODEL_ARCHITECT_DESC = "Arkitekten"
    MODEL_CODER_DESC = "Kodaren"


# Backend configuration
BACKEND_URL = os.getenv("SIMONS_AI_BACKEND_URL", "ws://localhost:8000/api/chat")
RECONNECT_DELAY = 2.0  # seconds between reconnect attempts
MAX_RECONNECT_ATTEMPTS = 5
TIMEOUT = 120.0  # seconds for WebSocket timeout (models kan ta 15-20s)


def get_backend_url() -> str:
    """Return the backend WebSocket URL"""
    return BACKEND_URL


def should_reconnect(error: Exception) -> bool:
    """
    Determine if reconnect should be attempted based on error type.
    """
    error_msg = str(error).lower()

    # Reconnect on connection errors
    if "connection" in error_msg or "disconnect" in error_msg:
        return True

    # Reconnect on timeout errors
    if "timeout" in error_msg or "timed out" in error_msg:
        return True

    # Don't reconnect on protocol errors or authentication errors
    return not ("protocol" in error_msg or "auth" in error_msg or "invalid" in error_msg)
