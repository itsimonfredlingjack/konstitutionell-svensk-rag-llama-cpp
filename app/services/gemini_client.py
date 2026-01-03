"""
Gemini API Client - Fast cloud-based inference
Handles communication with Google's Gemini API for instant responses

Environment:
    GEMINI_API_KEY - API key from https://makersuite.google.com/app/apikey
"""

import asyncio
import time
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
import httpx
import json
import os
from pathlib import Path

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Load .env file if it exists
def _load_env():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value

_load_env()

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.0-flash-exp"  # Fast model for interactive use

# Log warning if API key is missing
if not GEMINI_API_KEY:
    logger.warning(
        "⚠️  GEMINI_API_KEY missing. Fallback to local-only mode. "
        "Set GEMINI_API_KEY in .env for FAST mode cloud inference."
    )

# Timeouts
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0


@dataclass
class GeminiStats:
    """Statistics from Gemini API response"""
    tokens_generated: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    start_time: float = 0.0
    first_token_time: Optional[float] = None
    end_time: float = 0.0

    @property
    def total_duration_ms(self) -> int:
        if self.end_time and self.start_time:
            return int((self.end_time - self.start_time) * 1000)
        return 0

    @property
    def tokens_per_second(self) -> float:
        duration_s = (self.end_time - self.start_time) if self.end_time else 0
        if duration_s > 0:
            return self.tokens_generated / duration_s
        return 0.0


class GeminiError(Exception):
    """Base exception for Gemini errors"""
    pass


class GeminiConnectionError(GeminiError):
    """Connection to Gemini failed"""
    pass


class GeminiAPIError(GeminiError):
    """Gemini API returned an error"""
    pass


class GeminiClient:
    """
    Async client for Google Gemini API with streaming support.

    Used for FAST mode - immediate responses without GPU load.
    """

    def __init__(self, api_key: str = GEMINI_API_KEY, model: str = GEMINI_MODEL):
        self.api_key = api_key
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured"""
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT,
                    read=READ_TIMEOUT,
                    write=30.0,
                    pool=5.0
                )
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def is_connected(self) -> bool:
        """Check if Gemini API is reachable and configured"""
        if not self.is_configured:
            logger.warning("Gemini API key not configured")
            return False

        try:
            client = await self._get_client()
            # Simple check - list models
            response = await client.get(
                f"{GEMINI_BASE_URL}/models",
                params={"key": self.api_key},
                timeout=CONNECT_TIMEOUT
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Gemini connection check failed: {e}")
            return False

    def _build_messages(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None
    ) -> tuple[list[dict], Optional[dict]]:
        """Convert chat messages to Gemini format"""
        gemini_contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # Gemini uses system_instruction separately
                system_instruction = {"parts": [{"text": content}]}
            elif role == "user":
                gemini_contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif role == "assistant":
                gemini_contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })

        # Apply external system prompt if provided and none in messages
        if system_prompt and not system_instruction:
            system_instruction = {"parts": [{"text": system_prompt}]}

        return gemini_contents, system_instruction

    async def chat_stream(
        self,
        messages: list[dict],
        request_id: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> AsyncGenerator[tuple[str, Optional[GeminiStats]], None]:
        """
        Stream chat completion tokens from Gemini.

        Yields:
            Tuple of (token_content, stats)
            - During streaming: (token, None)
            - Final yield: ("", GeminiStats)
        """
        if not self.is_configured:
            raise GeminiError("Gemini API key not configured")

        stats = GeminiStats(start_time=time.time())

        # Build request
        contents, system_instruction = self._build_messages(messages, system_prompt)

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = system_instruction

        url = f"{GEMINI_BASE_URL}/models/{self.model}:streamGenerateContent"

        logger.info(f"[{request_id}] Starting Gemini chat with {self.model}")

        try:
            client = await self._get_client()

            async with client.stream(
                "POST",
                url,
                params={"key": self.api_key, "alt": "sse"},
                json=payload
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Gemini error {response.status_code}: {error_text}")
                    raise GeminiAPIError(f"Gemini returned {response.status_code}: {error_text}")

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])  # Remove "data: " prefix
                    except json.JSONDecodeError:
                        continue

                    # Extract text from candidates
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        for part in parts:
                            text = part.get("text", "")
                            if text:
                                if stats.first_token_time is None:
                                    stats.first_token_time = time.time()
                                stats.tokens_generated += len(text.split())  # Rough estimate
                                yield text, None

                    # Check for usage metadata (final chunk)
                    usage = data.get("usageMetadata", {})
                    if usage:
                        stats.prompt_tokens = usage.get("promptTokenCount", 0)
                        stats.tokens_generated = usage.get("candidatesTokenCount", 0)
                        stats.total_tokens = usage.get("totalTokenCount", 0)

        except httpx.ConnectError as e:
            raise GeminiConnectionError(
                "Cannot connect to Gemini API. Check internet connection."
            ) from e

        except httpx.ReadTimeout as e:
            stats.end_time = time.time()
            raise GeminiError(f"Request timed out after {READ_TIMEOUT}s") from e

        # Final yield with stats
        stats.end_time = time.time()
        logger.info(
            f"[{request_id}] Gemini completed: {stats.tokens_generated} tokens "
            f"in {stats.total_duration_ms}ms ({stats.tokens_per_second:.1f} tok/s)"
        )
        yield "", stats

    async def chat_complete(
        self,
        messages: list[dict],
        request_id: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> tuple[str, GeminiStats]:
        """
        Non-streaming chat completion.
        Returns complete response and stats.
        """
        full_response = []
        stats = None

        async for token, final_stats in self.chat_stream(
            messages, request_id, system_prompt, temperature, max_tokens
        ):
            if token:
                full_response.append(token)
            if final_stats:
                stats = final_stats

        return "".join(full_response), stats


# Global client instance
gemini_client = GeminiClient()


async def get_gemini_client() -> GeminiClient:
    """Dependency injection helper"""
    return gemini_client
