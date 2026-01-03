"""
Claude Code UI Client - WebSocket integration
Handles communication with Claude Code UI server via WebSocket

Environment:
    CLAUDE_UI_URL - URL to Claude Code UI server (default: http://localhost:3001)
    CLAUDE_UI_TOKEN - JWT token for authentication (optional, uses platform mode if not set)
    CLAUDE_MODEL - Claude model to use (default: sonnet)
"""

import asyncio
import time
import json
import os
from typing import AsyncGenerator, Optional
from dataclasses import dataclass
from pathlib import Path
import websockets
from websockets.client import WebSocketClientProtocol

from ..utils.logging import get_logger

logger = get_logger(__name__)

# Load .env file if it exists
def _load_env():
    """Load environment variables from .env and .env.local files"""
    for env_file in [".env", ".env.local"]:
        env_path = Path(__file__).parent.parent.parent / env_file
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

# Claude Code UI configuration
CLAUDE_UI_URL = os.getenv("CLAUDE_UI_URL", "http://localhost:3001")
CLAUDE_UI_WS_URL = CLAUDE_UI_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
CLAUDE_UI_TOKEN = os.getenv("CLAUDE_UI_TOKEN", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")

# Timeouts
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 120.0


@dataclass
class ClaudeStats:
    """Statistics from Claude CLI response"""
    tokens_generated: int = 0
    prompt_tokens: int = 0
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


class ClaudeError(Exception):
    """Base exception for Claude errors"""
    pass


class ClaudeConnectionError(ClaudeError):
    """Connection to Claude CLI failed"""
    pass


class ClaudeTimeoutError(ClaudeError):
    """Operation timed out"""
    pass


class ClaudeClient:
    """
    Async client for Claude CLI with streaming support.

    Uses Claude Code CLI in --print mode with stream-json format
    for real-time token streaming.
    """

    def __init__(self, ui_url: str = CLAUDE_UI_URL, token: str = CLAUDE_UI_TOKEN, model: str = CLAUDE_MODEL):
        self.ui_url = ui_url
        self.ws_url = ui_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        self.token = token
        self.model = model
        self._ws: Optional[WebSocketClientProtocol] = None

    @property
    def is_configured(self) -> bool:
        """Check if Claude UI URL is configured"""
        return bool(self.ui_url)

    async def is_connected(self) -> bool:
        """Check if Claude Code UI WebSocket is reachable"""
        if not self.is_configured:
            logger.warning("Claude UI URL not configured")
            return False

        try:
            # Try to connect to WebSocket
            ws_url = self.ui_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
            async with websockets.connect(
                ws_url,
                timeout=CONNECT_TIMEOUT,
                extra_headers={"Authorization": f"Bearer {self.token}"} if self.token else {}
            ) as ws:
                return True
        except Exception as e:
            logger.warning(f"Claude UI connection check failed: {e}")
            return False

    def _build_command_from_messages(self, messages: list[dict], system_prompt: Optional[str] = None) -> str:
        """Extract the latest user message from conversation"""
        # Find the last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        
        # If no user message, use system prompt or empty
        return system_prompt or ""

    async def chat_stream(
        self,
        messages: list[dict],
        request_id: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> AsyncGenerator[tuple[str, Optional[ClaudeStats]], None]:
        """
        Stream chat completion tokens from Claude CLI.

        Yields:
            Tuple of (token_content, stats)
            - During streaming: (token, None)
            - Final yield: ("", ClaudeStats)
        """
        if not self.is_configured:
            raise ClaudeError("Claude CLI not found")

        stats = ClaudeStats(start_time=time.time())

        # Extract command from messages
        command = self._build_command_from_messages(messages, system_prompt)

        # Build WebSocket message
        ws_message = {
            "type": "claude-command",
            "command": command,
            "options": {
                "model": self.model,
                "sessionId": request_id,  # Use request_id as session ID
                "projectPath": os.getcwd()  # Use current working directory
            }
        }

        logger.info(f"[{request_id}] Starting Claude UI chat with {self.model}")

        try:
            # Connect to WebSocket
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            async with websockets.connect(
                self.ws_url,
                timeout=CONNECT_TIMEOUT,
                extra_headers=headers
            ) as ws:
                # Send command
                await ws.send(json.dumps(ws_message))

                # Read streaming responses
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        # Handle different message types from Claude UI
                        if data.get("type") == "claude-response":
                            # Content chunk
                            content = data.get("data", {}).get("content", "")
                            if content:
                                if stats.first_token_time is None:
                                    stats.first_token_time = time.time()
                                stats.tokens_generated += len(content) // 4
                                yield content, None
                        
                        elif data.get("type") == "result":
                            # Final result
                            content = data.get("content", "")
                            if content:
                                if stats.first_token_time is None:
                                    stats.first_token_time = time.time()
                                stats.tokens_generated += len(content) // 4
                                yield content, None
                            break
                        
                        elif data.get("type") == "error":
                            error_msg = data.get("error", "Unknown error")
                            logger.error(f"Claude UI error: {error_msg}")
                            raise ClaudeError(f"Claude UI error: {error_msg}")

                    except json.JSONDecodeError:
                        # Try to treat as plain text
                        if message:
                            if stats.first_token_time is None:
                                stats.first_token_time = time.time()
                            stats.tokens_generated += len(message) // 4
                            yield message, None

        except asyncio.TimeoutError:
            stats.end_time = time.time()
            raise ClaudeTimeoutError(f"Request timed out after {READ_TIMEOUT}s")

        except Exception as e:
            stats.end_time = time.time()
            raise ClaudeError(f"Claude CLI error: {e}") from e

        # Final yield with stats
        stats.end_time = time.time()
        logger.info(
            f"[{request_id}] Claude completed: {stats.tokens_generated} tokens "
            f"in {stats.total_duration_ms}ms ({stats.tokens_per_second:.1f} tok/s)"
        )
        yield "", stats

    async def close(self) -> None:
        """Close WebSocket connection"""
        if self._ws:
            await self._ws.close()
            self._ws = None


# Global client instance
claude_client = ClaudeClient()


async def get_claude_client() -> ClaudeClient:
    """Dependency injection helper"""
    return claude_client
