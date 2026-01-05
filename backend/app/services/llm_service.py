"""
LLM Service - Ollama Wrapper for Constitutional AI
Handles all LLM interactions with streaming and model fallback
"""

from typing import AsyncGenerator, Optional, List
from dataclasses import dataclass
from functools import lru_cache
import httpx
import json
import asyncio

from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from ..core.exceptions import (
    LLMTimeoutError,
    LLMConnectionError,
    LLMModelNotFoundError,
)
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMConfig:
    """
    Configuration for LLM service.

    All timeouts and model settings configurable.
    """

    primary_model: str
    fallback_model: str
    timeout: float = 60.0

    # Model options
    temperature: float = 0.5
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    num_predict: int = 512

    # Connection settings
    connect_timeout: float = 5.0
    pool_connections: int = 5


@dataclass
class StreamStats:
    """
    Statistics collected during LLM streaming.
    """

    tokens_generated: int = 0
    start_time: float = 0.0
    first_token_time: Optional[float] = None
    end_time: float = 0.0
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0
    model_used: str = ""

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


class LLMService(BaseService):
    """
    LLM Service - Handles all Ollama interactions.

    Features:
    - Streaming chat completions
    - Model fallback on timeout
    - Configurable models per mode
    - Connection pooling
    - Model unloading to free VRAM

    Thread Safety:
        - httpx.AsyncClient is async-safe
        - No shared mutable state between coroutines
    """

    # LLM Service API endpoints (llama-server = OpenAI-compatible)
    # Use llama-server (port 8080) if enabled, otherwise fall back to default Ollama (port 11434)
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_CHAT_ENDPOINT = f"{OLLAMA_BASE_URL}/api/chat"
    OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_BASE_URL}/api/generate"
    OLLAMA_TAGS_ENDPOINT = f"{OLLAMA_BASE_URL}/api/tags"
    OLLAMA_PS_ENDPOINT = f"{OLLAMA_BASE_URL}/api/ps"
    OLLAMA_SHOW_ENDPOINT = f"{OLLAMA_BASE_URL}/api/show"
    OLLAMA_VERSION_ENDPOINT = f"{OLLAMA_BASE_URL}/api/version"

    def _get_base_url(self) -> str:
        """Get base URL based on configuration"""
        if self.config.llama_server_enabled:
            return self.config.llama_server_base_url
        return self.OLLAMA_BASE_URL

    def _get_chat_endpoint(self) -> str:
        """Get chat endpoint based on configuration"""
        base_url = self._get_base_url().rstrip("/")
        if self.config.llama_server_enabled:
            # If base_url already includes /v1, don't append it again.
            if base_url.endswith("/v1"):
                return f"{base_url}/chat/completions"
            return f"{base_url}/v1/chat/completions"
        return self.OLLAMA_CHAT_ENDPOINT

    def _get_models_endpoint(self) -> str:
        """Get models endpoint based on configuration"""
        base_url = self._get_base_url().rstrip("/")
        if self.config.llama_server_enabled:
            if base_url.endswith("/v1"):
                return f"{base_url}/models"
            return f"{base_url}/v1/models"
        return self.OLLAMA_TAGS_ENDPOINT

    def _get_health_endpoint(self) -> str:
        """Get health endpoint based on configuration"""
        if self.config.llama_server_enabled:
            return self._get_models_endpoint()
        return self.OLLAMA_TAGS_ENDPOINT

    def __init__(self, config: ConfigService):
        """
        Initialize LLM Service.

        Args:
            config: ConfigService for configuration access
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None
        self._config: LLMConfig = self._build_default_config()
        self.logger.info(f"LLM Service initialized (primary: {self._config.primary_model})")

    def _build_default_config(self) -> LLMConfig:
        """
        Build default LLM configuration from ConfigService.
        """
        return LLMConfig(
            primary_model=self.config.constitutional_model,
            fallback_model=self.config.constitutional_fallback,
            timeout=self.config.llm_timeout,
            connect_timeout=5.0,
            pool_connections=5,
        )

    async def initialize(self) -> None:
        """
        Initialize HTTP client for LLM communication.

        Creates async httpx client with connection pooling.
        """
        if self._client is None:
            base_url = self._get_base_url()
            timeout = (
                self.config.llama_server_timeout
                if self.config.llama_server_enabled
                else self._config.timeout + 30.0
            )

            self._client = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(timeout),
                limits=httpx.Limits(
                    max_keepalive_connections=self._config.pool_connections,
                    max_connections=10,
                ),
            )
            self.logger.info(f"LLM Service HTTP client initialized for {base_url}")
        self._mark_initialized()

    async def health_check(self) -> bool:
        """
        Check if LLM service is healthy.

        Returns:
            True if LLM is reachable, False otherwise
        """
        try:
            await self.ensure_initialized()
            health_endpoint = self._get_health_endpoint()
            response = await self._client.get(health_endpoint, timeout=2.0)
            is_healthy = response.status_code == 200
            self.logger.info(f"LLM health check: {'OK' if is_healthy else 'FAILED'}")
            return is_healthy
        except Exception as e:
            self.logger.error(f"LLM health check failed: {e}")
            return False

    async def close(self) -> None:
        """
        Cleanup HTTP client.

        Closes connection pool and releases resources.
        """
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            self.logger.info("LLM Service HTTP client closed")

        self._mark_uninitialized()

    async def is_connected(self) -> bool:
        """
        Check if LLM server is reachable.

        Lightweight check without full health check.

        Returns:
            True if reachable, False otherwise
        """
        try:
            await self.ensure_initialized()
            models_endpoint = self._get_models_endpoint()
            response = await self._client.get(models_endpoint, timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    async def get_version(self) -> Optional[str]:
        """
        Get LLM server version.

        Returns:
            Version string or None if unavailable
        """
        try:
            await self.ensure_initialized()
            # Only available for default Ollama, not llama-server
            if not self.config.llama_server_enabled:
                response = await self._client.get(self.OLLAMA_VERSION_ENDPOINT)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("version")
        except Exception as e:
            self.logger.error(f"Failed to get LLM version: {e}")
        return None

    async def list_models(self) -> List[str]:
        """
        List available models.

        Returns:
            List of model names
        """
        try:
            await self.ensure_initialized()
            models_endpoint = self._get_models_endpoint()
            response = await self._client.get(models_endpoint)
            if response.status_code == 200:
                data = response.json()
                if self.config.llama_server_enabled:
                    # OpenAI-compatible format: data["data"][0]["id"]
                    return [m.get("id", "") for m in data.get("data", [])]
                else:
                    # Ollama format: data["models"][0]["name"]
                    return [m["name"] for m in data.get("models", [])]
            return []
        except Exception as e:
            self.logger.error(f"Failed to list LLM models: {e}")
            return []

    async def list_running_models(self) -> List[dict]:
        """
        List currently loaded/running models.

        Returns:
            List of model info with name, size, etc.
        """
        try:
            # Only available for default Ollama, not llama-server
            if not self.config.llama_server_enabled:
                await self.ensure_initialized()
                response = await self._client.get(self.OLLAMA_PS_ENDPOINT)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("models", [])
            return []
        except Exception as e:
            self.logger.error(f"Failed to list running models: {e}")
            return []

    async def is_model_available(self, model_name: str) -> bool:
        """
        Check if a specific model is downloaded.

        Args:
            model_name: Model name to check (e.g., "ministral-3:14b")

        Returns:
            True if model is available, False otherwise
        """
        models = await self.list_models()
        return any(model_name in m or m.startswith(model_name.split(":")[0]) for m in models)

    async def is_model_loaded(self, model_name: str) -> bool:
        """
        Check if model is currently loaded in memory.

        Args:
            model_name: Model name to check

        Returns:
            True if loaded, False otherwise
        """
        running = await self.list_running_models()
        return any(model_name in m.get("name", "") for m in running)

    async def unload_model(self, model_name: str) -> bool:
        """
        Unload a specific model from VRAM.

        Sends an empty generate request with keep_alive=0 to unload model.

        Args:
            model_name: Model name to unload

        Returns:
            True if successful, False otherwise
        """
        try:
            await self.ensure_initialized()
            response = await self._client.post(
                self.OLLAMA_GENERATE_ENDPOINT,
                json={"model": model_name, "prompt": "", "keep_alive": 0},
                timeout=10.0,
            )
            is_success = response.status_code == 200
            if is_success:
                self.logger.info(f"Unloaded model: {model_name}")
            return is_success
        except Exception as e:
            self.logger.error(f"Failed to unload {model_name}: {e}")
            return False

    async def unload_other_models(self, keep_model: str) -> List[str]:
        """
        Unload all models except one we want to keep.

        Useful for managing VRAM on GPUs with limited memory.

        Args:
            keep_model: Model name to keep in memory

        Returns:
            List of models that were unloaded
        """
        running = await self.list_running_models()
        unloaded = []

        for model_info in running:
            model_name = model_info.get("name", "")
            if model_name and keep_model not in model_name:
                if await self.unload_model(model_name):
                    unloaded.append(model_name)

        if unloaded:
            self.logger.info(f"Auto-unloaded models to free VRAM: {unloaded}")

        return unloaded

    async def chat_stream(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        config_override: Optional[dict] = None,
    ) -> AsyncGenerator[tuple[str, Optional[StreamStats]], None]:
        """
        Stream chat completion tokens.

        Yields:
            Tuple of (token_content, stats)
            - During streaming: (token, None)
            - Final yield: ("", StreamStats)

        Args:
            messages: Chat messages in OpenAI format
            model: Model name (uses default if None)
            config_override: Override model config (temperature, etc.)

        Raises:
            LLMTimeoutError: If request times out
            LLMConnectionError: If connection fails
            LLMModelNotFoundError: If model not available
        """
        await self.ensure_initialized()

        # Use provided model or default
        model_to_use = model or self._config.primary_model

        # Build request based on API format
        if self.config.llama_server_enabled:
            # OpenAI-compatible format for llama-server
            payload = {
                "model": model_to_use,
                "messages": messages,
                "stream": True,
                "temperature": config_override.get("temperature", self._config.temperature)
                if config_override
                else self._config.temperature,
                "top_p": config_override.get("top_p", self._config.top_p)
                if config_override
                else self._config.top_p,
                "max_tokens": config_override.get("num_predict", self._config.num_predict)
                if config_override
                else self._config.num_predict,
            }
        else:
            # Ollama format
            model_options = {
                "temperature": config_override.get("temperature", self._config.temperature)
                if config_override
                else self._config.temperature,
                "top_p": config_override.get("top_p", self._config.top_p)
                if config_override
                else self._config.top_p,
                "repeat_penalty": config_override.get("repeat_penalty", self._config.repeat_penalty)
                if config_override
                else self._config.repeat_penalty,
                "num_predict": config_override.get("num_predict", self._config.num_predict)
                if config_override
                else self._config.num_predict,
            }
            payload = {
                "model": model_to_use,
                "messages": messages,
                "stream": True,
                "options": model_options,
            }

        stats = StreamStats(start_time=0.0, model_used=model_to_use)

        try:
            chat_endpoint = self._get_chat_endpoint()
            timeout = (
                self.config.llama_server_timeout
                if self.config.llama_server_enabled
                else self._config.timeout + 30.0
            )

            self.logger.info(
                f"Starting LLM chat stream with {model_to_use} (endpoint: {chat_endpoint})"
            )

            async with self._client.stream(
                "POST",
                chat_endpoint,
                json=payload,
                timeout=httpx.Timeout(timeout),
            ) as response:
                if response.status_code == 404:
                    raise LLMModelNotFoundError(f"Model {model_to_use} not found")

                if response.status_code != 200:
                    error_text = await response.aread()
                    self.logger.error(f"LLM error {response.status_code}: {error_text}")
                    raise LLMConnectionError(f"LLM returned {response.status_code}: {error_text}")

                # Process streaming response
                first_token = False
                if self.config.llama_server_enabled:
                    # OpenAI-compatible format: "data: {...}" lines
                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        if not line.startswith("data: "):
                            continue

                        line = line[6:]  # Remove "data: " prefix

                        if line.strip() == "[DONE]":
                            break

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Set start time on first token
                        if not first_token:
                            stats.start_time = asyncio.get_event_loop().time()
                            stats.first_token_time = stats.start_time
                            first_token = True

                        # Extract token content (OpenAI format)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")

                        if content:
                            stats.tokens_generated += 1
                            yield content, None

                        # Check for completion
                        finish_reason = data.get("choices", [{}])[0].get("finish_reason")
                        if finish_reason:
                            stats.end_time = asyncio.get_event_loop().time()

                            # Extract usage stats (OpenAI format)
                            usage = data.get("usage", {})
                            stats.prompt_eval_count = usage.get("prompt_tokens", 0)

                            self.logger.info(
                                f"LLM chat complete: {stats.tokens_generated} tokens "
                                f"in {stats.total_duration_ms}ms "
                                f"({stats.tokens_per_second:.1f} tok/s)"
                            )

                            # Final yield with stats
                            yield "", stats
                            break
                else:
                    # Ollama format (existing code)
                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Set start time on first token
                        if not first_token:
                            stats.start_time = asyncio.get_event_loop().time()
                            stats.first_token_time = stats.start_time
                            first_token = True

                        # Extract token content (Ollama format)
                        message = data.get("message", {})
                        content = message.get("content", "")

                        if content:
                            stats.tokens_generated += 1
                            yield content, None

                        # Check for completion
                        if data.get("done", False):
                            stats.end_time = asyncio.get_event_loop().time()

                            # Extract final stats from Ollama
                            stats.prompt_eval_count = data.get("prompt_eval_count", 0)
                            stats.prompt_eval_duration_ns = data.get("prompt_eval_duration", 0)

                            self.logger.info(
                                f"LLM chat complete: {stats.tokens_generated} tokens "
                                f"in {stats.total_duration_ms}ms "
                                f"({stats.tokens_per_second:.1f} tok/s)"
                            )

                            # Final yield with stats
                            yield "", stats
                            break

        except httpx.TimeoutException as e:
            self.logger.error(f"LLM request timed out: {e}")
            raise LLMTimeoutError("Request timed out") from e

        except httpx.ConnectError as e:
            self.logger.error(f"LLM connection failed: {e}")
            raise LLMConnectionError("Cannot connect to LLM server") from e

    async def chat_complete(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        config_override: Optional[dict] = None,
    ) -> tuple[str, StreamStats]:
        """
        Non-streaming chat completion.

        Collects all streaming tokens and returns complete response.

        Returns:
            Tuple of (full_response, stats)
        """
        full_response = []
        stats = None

        async for token, final_stats in self.chat_stream(messages, model, config_override):
            if token:
                full_response.append(token)
            if final_stats:
                stats = final_stats

        return "".join(full_response), stats

    async def chat_with_fallback(
        self,
        messages: List[dict],
        model: Optional[str] = None,
        config_override: Optional[dict] = None,
    ) -> AsyncGenerator[tuple[str, Optional[StreamStats]], None]:
        """
        Stream chat completion with automatic model fallback on timeout.

        If primary model times out, automatically tries fallback model.
        Emits fallback event before switching models.

        Yields:
            Tuple of (event, stats)
            Events can be:
            - ("token", stats): LLM token
            - ("fallback", stats): Fallback triggered
            - ("done", stats): Completion with final stats
        """
        primary_model = model or self._config.primary_model

        # Yield fallback event before trying primary
        yield "start", None
        self.logger.info(f"Attempting primary model: {primary_model}")

        try:
            async for token, stats in self.chat_stream(messages, primary_model, config_override):
                if token:
                    yield f"token:{token}", stats
                else:
                    yield "done", stats
                    return

        except LLMTimeoutError as e:
            # Try fallback model
            self.logger.warning(
                f"Primary model timed out, trying fallback: {self._config.fallback_model}"
            )
            yield f"fallback:primary→{self._config.fallback_model}", None

            try:
                async for token, stats in self.chat_stream(
                    messages, self._config.fallback_model, config_override
                ):
                    if token:
                        yield f"token:{token}", stats
                    else:
                        yield "done", stats
                        return

            except Exception as fallback_error:
                self.logger.error(f"Fallback model also failed: {fallback_error}")
                # Re-raise original timeout error
                raise e

        except Exception as e:
            self.logger.error(f"Chat with fallback failed: {e}")
            raise

    def get_mode_config(self, mode: str) -> dict:
        """
        Get model configuration for a specific response mode.

        Maps mode names to pre-configured model settings.

        Args:
            mode: Response mode (evidence, assist, chat)

        Returns:
            Dictionary with model configuration
        """
        mode_config_map = {
            "evidence": self.config.get_mode_config("evidence"),
            "assist": self.config.get_mode_config("assist"),
            "chat": self.config.get_mode_config("chat"),
        }

        return mode_config_map.get(mode.lower(), mode_config_map["assist"])


@lru_cache()
def get_llm_service(config: Optional[ConfigService] = None) -> LLMService:
    """
    Get singleton LLM Service instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Singleton LLMService instance
    """
    if config is None:
        config = get_config_service()

    return LLMService(config)
