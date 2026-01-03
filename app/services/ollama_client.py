"""
Ollama Client - Streaming chat interface
Handles communication with local Ollama server for THINK/CHILL models
"""

import asyncio
import time
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
import httpx
import json

from ..models.Backend_Agent_Prompts import ModelProfile, get_profile, profile_manager, ProfileId
from ..config import (
    PLANNER_CONFIG,
    GENERALIST_CONFIG,
    MODEL_PLANNER,
    MODEL_GENERALIST,
)
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Ollama API configuration
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CHAT_ENDPOINT = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_ENDPOINT = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_PS_ENDPOINT = f"{OLLAMA_BASE_URL}/api/ps"
OLLAMA_SHOW_ENDPOINT = f"{OLLAMA_BASE_URL}/api/show"

# Timeouts
CONNECT_TIMEOUT = 5.0  # seconds
READ_TIMEOUT = 120.0  # seconds for streaming (models can be slow to start)
WARMUP_TIMEOUT = 60.0  # seconds for model loading


@dataclass
class StreamStats:
    """Statistics collected during streaming"""
    tokens_generated: int = 0
    start_time: float = 0.0
    first_token_time: Optional[float] = None
    end_time: float = 0.0
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0

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

    @property
    def time_to_first_token_ms(self) -> Optional[int]:
        if self.first_token_time and self.start_time:
            return int((self.first_token_time - self.start_time) * 1000)
        return None


class OllamaError(Exception):
    """Base exception for Ollama errors"""
    pass


class OllamaConnectionError(OllamaError):
    """Connection to Ollama failed"""
    pass


class OllamaModelNotFoundError(OllamaError):
    """Requested model not available"""
    pass


class OllamaTimeoutError(OllamaError):
    """Operation timed out"""
    pass


class OllamaClient:
    """
    Async client for Ollama API with streaming support.

    Handles:
    - Streaming chat completions
    - Model availability checking
    - Model loading/unloading tracking
    - Connection health checks
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

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

    def _get_model_options(self, profile: ModelProfile) -> dict:
        """
        Get model-specific configuration options.
        Uses optimized configs for PLANNER and GENERALIST.
        """
        # PLANNER (PHI4-reasoning 14B)
        if MODEL_PLANNER in profile.model or "planner" in profile.model:
            logger.info(f"Using PLANNER_CONFIG for {profile.model} with {PLANNER_CONFIG['num_ctx']} context")
            return PLANNER_CONFIG.copy()

        # GENERALIST (GPT-OSS 20B)
        if MODEL_GENERALIST in profile.model or "generalist" in profile.model:
            logger.info(f"Using GENERALIST_CONFIG for {profile.model} with {GENERALIST_CONFIG['num_ctx']} context")
            return GENERALIST_CONFIG.copy()

        # Fallback to profile defaults
        return {
            "temperature": profile.temperature,
            "top_p": profile.top_p,
            "repeat_penalty": profile.repeat_penalty,
            "num_predict": profile.max_tokens,
            "num_ctx": profile.context_length,
        }

    async def close(self) -> None:
        """Close the HTTP client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def is_connected(self) -> bool:
        """Check if Ollama server is reachable"""
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/api/tags",
                timeout=CONNECT_TIMEOUT
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama connection check failed: {e}")
            return False

    async def get_version(self) -> Optional[str]:
        """Get Ollama version"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/version")
            if response.status_code == 200:
                data = response.json()
                return data.get("version")
        except Exception:
            pass
        return None

    async def list_models(self) -> list[str]:
        """List available models (downloaded)"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
        return []

    async def list_running_models(self) -> list[dict]:
        """List currently loaded/running models"""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/ps")
            if response.status_code == 200:
                data = response.json()
                return data.get("models", [])
        except Exception as e:
            logger.error(f"Failed to list running models: {e}")
        return []

    async def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is downloaded"""
        models = await self.list_models()
        # Handle both full names and short names
        return any(
            model_name in m or m.startswith(model_name.split(":")[0])
            for m in models
        )

    async def is_model_loaded(self, model_name: str) -> bool:
        """Check if model is currently loaded in memory"""
        running = await self.list_running_models()
        return any(model_name in m.get("name", "") for m in running)

    async def unload_model(self, model_name: str) -> bool:
        """Unload a specific model from VRAM by setting keep_alive=0"""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model_name,
                    "prompt": "",
                    "keep_alive": 0
                },
                timeout=10.0
            )
            logger.info(f"Unloaded model: {model_name}")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to unload {model_name}: {e}")
            return False

    async def unload_other_models(self, keep_model: str) -> list[str]:
        """Unload all models except the one we want to keep"""
        running = await self.list_running_models()
        unloaded = []
        for model_info in running:
            model_name = model_info.get("name", "")
            if model_name and keep_model not in model_name:
                if await self.unload_model(model_name):
                    unloaded.append(model_name)
        return unloaded

    async def warmup_model(self, profile: ModelProfile) -> bool:
        """
        Warm up a model by sending a minimal request.
        This pre-loads the model into GPU memory.
        """
        logger.info(f"Warming up model: {profile.model}")
        profile_manager.set_loading(profile.id)

        # Auto-unload andra modeller först (RTX 4070 kan bara ha en)
        unloaded = await self.unload_other_models(profile.model)
        if unloaded:
            logger.info(f"Auto-unloaded models to free VRAM: {unloaded}")

        try:
            client = await self._get_client()

            # Send minimal generate request to load model
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model": profile.model,
                    "prompt": "Hi",
                    "options": {"num_predict": 1}
                },
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT,
                    read=WARMUP_TIMEOUT,
                    write=30.0,
                    pool=5.0
                )
            ) as response:
                if response.status_code != 200:
                    logger.error(f"Warmup failed: {response.status_code}")
                    return False

                # Consume stream to ensure model loads
                async for _ in response.aiter_lines():
                    pass

            profile_manager.set_active(profile.id)
            logger.info(f"Model warmed up: {profile.model}")
            return True

        except Exception as e:
            logger.error(f"Warmup error for {profile.model}: {e}")
            return False

    async def chat_stream(
        self,
        profile: ModelProfile,
        messages: list[dict],
        request_id: str
    ) -> AsyncGenerator[tuple[str, Optional[StreamStats]], None]:
        """
        Stream chat completion tokens.

        Yields:
            Tuple of (token_content, stats)
            - During streaming: (token, None)
            - Final yield: ("", StreamStats)
        """
        stats = StreamStats(start_time=time.time())

        # Get model-specific configuration
        model_options = self._get_model_options(profile)

        # Build request payload
        payload = {
            "model": profile.model,
            "messages": messages,
            "stream": True,
            "options": model_options
        }

        logger.info(f"[{request_id}] Starting chat with {profile.model}")

        try:
            client = await self._get_client()

            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT,
                    read=READ_TIMEOUT,
                    write=30.0,
                    pool=5.0
                )
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"Ollama error {response.status_code}: {error_text}")

                    if response.status_code == 404:
                        raise OllamaModelNotFoundError(
                            f"Model {profile.model} not found. Run: ollama pull {profile.model}"
                        )
                    raise OllamaError(f"Ollama returned {response.status_code}")

                # Mark model as active once we start receiving
                profile_manager.set_active(profile.id)

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Extract token content
                    message = data.get("message", {})
                    content = message.get("content", "")

                    if content:
                        # Track first token timing
                        if stats.first_token_time is None:
                            stats.first_token_time = time.time()

                        stats.tokens_generated += 1
                        yield content, None

                    # Check for completion
                    if data.get("done", False):
                        stats.end_time = time.time()

                        # Extract final stats from Ollama
                        stats.prompt_eval_count = data.get("prompt_eval_count", 0)
                        stats.prompt_eval_duration_ns = data.get("prompt_eval_duration", 0)

                        logger.info(
                            f"[{request_id}] Completed: {stats.tokens_generated} tokens "
                            f"in {stats.total_duration_ms}ms "
                            f"({stats.tokens_per_second:.1f} tok/s)"
                        )
                        break

        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                "Cannot connect to Ollama. Is it running? Try: ollama serve"
            ) from e

        except httpx.ReadTimeout as e:
            stats.end_time = time.time()
            raise OllamaTimeoutError(
                f"Request timed out after {READ_TIMEOUT}s"
            ) from e

        # Final yield with stats
        if stats.end_time == 0:
            stats.end_time = time.time()

        yield "", stats

    async def chat_complete(
        self,
        profile: ModelProfile,
        messages: list[dict],
        request_id: str
    ) -> tuple[str, StreamStats]:
        """
        Non-streaming chat completion.
        Returns complete response and stats.
        """
        full_response = []
        stats = None

        async for token, final_stats in self.chat_stream(profile, messages, request_id):
            if token:
                full_response.append(token)
            if final_stats:
                stats = final_stats

        return "".join(full_response), stats


# Global client instance
ollama_client = OllamaClient()


async def get_ollama_client() -> OllamaClient:
    """Dependency injection helper"""
    return ollama_client
