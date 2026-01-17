"""
WebSocket client for Simons AI backend
Handles connection, streaming, and reconnect logic
"""

import asyncio
import json
from collections.abc import AsyncGenerator

import websockets
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
)

from .config import (
    MAX_RECONNECT_ATTEMPTS,
    MODEL_ARCHITECT,
    RECONNECT_DELAY,
    TIMEOUT,
    get_backend_url,
    should_reconnect,
)

# NOTE: show_status removed - conflicts with Rich Live alternate screen mode
# Status is now handled via state.status in main.py layout


class NERDYAIClient:
    """
    WebSocket client för Simons AI backend.
    Hanterar:
    - Anslutning till backend
    - Reconnect-logik vid disconnect
    - Token streaming
    - Error handling
    """

    def __init__(self):
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.url: str = get_backend_url()
        self.connected: bool = False
        self.current_mode: str | None = None  # "juridik" or "diarie"
        self.current_profile: str = MODEL_ARCHITECT  # Default: gpt-oss

    async def connect(self) -> None:
        """Ansluter till backend med retry-logik"""
        attempt = 0

        while attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                # Use asyncio.wait_for for timeout compatibility across websockets versions
                # Enable ping to detect dropped connections (heartbeat)
                self.websocket = await asyncio.wait_for(
                    websockets.connect(
                        self.url,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=10
                    ),
                    timeout=TIMEOUT,
                )
                self.connected = True
                return

            except asyncio.TimeoutError:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    raise ConnectionError(f"Timeout efter {TIMEOUT} sekunder") from None
                await asyncio.sleep(RECONNECT_DELAY)
            except Exception as e:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    raise e from None

                if should_reconnect(e):
                    await asyncio.sleep(RECONNECT_DELAY)
                else:
                    raise e from None

                if should_reconnect(e):
                    await asyncio.sleep(RECONNECT_DELAY)
                else:
                    raise

    async def send_message(self, text: str, profile: str | None = None) -> None:
        """Skickar meddelande till backend"""
        if not self.connected or not self.websocket:
            raise ConnectionError("Inte ansluten till backend")

        # Use current_profile if no profile specified
        active_profile = profile if profile else self.current_profile

        # Build message according to Antigravity protocol
        message = {"text": text, "profile": active_profile}

        try:
            await self.websocket.send(json.dumps(message))
        except (ConnectionClosed, ConnectionClosedError, ConnectionClosedOK) as e:
            self.connected = False
            raise ConnectionError(f"Anslutning stängd: {e}") from e
        except Exception as e:
            raise ConnectionError(f"Kunde inte skicka meddelande: {e}") from e

    async def receive_stream(self) -> AsyncGenerator[tuple[str, dict | None], None]:
        """
        Generator som streamar tokens från backend.
        Yields: (token, stats) tuples where stats is None until final message
        """
        if not self.connected or not self.websocket:
            raise ConnectionError("Inte ansluten till backend")

        final_stats = None
        try:
            while True:
                try:
                    raw_message = await self.websocket.recv()
                    data = json.loads(raw_message)

                    # Check if message is finished
                    if data.get("is_finished", False):
                        # Extract final stats
                        stats = data.get("stats", {})
                        if stats:
                            final_stats = stats
                        break

                    # Extract token text
                    token = data.get("text", "")
                    if token:
                        yield (token, None)

                except (ConnectionClosed, ConnectionClosedError, ConnectionClosedOK) as e:
                    self.connected = False
                    raise ConnectionError(f"Anslutning stängd: {e}") from e
                except json.JSONDecodeError:
                    # Skip invalid JSON
                    continue

            # Yield final stats if available
            if final_stats:
                yield ("", final_stats)

        except websockets.exceptions.WebSocketException as e:
            self.connected = False
            raise ConnectionError(f"WebSocket-fel: {e}") from e

    async def close(self) -> None:
        """Stänger anslutning snyggt"""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            finally:
                self.websocket = None
                self.connected = False

    def set_mode(self, mode: str | None) -> None:
        """Sätter aktuellt läge (juridik/diarie)"""
        self.current_mode = mode

    def get_mode(self) -> str | None:
        """Hämtar aktuellt läge"""
        return self.current_mode

    def set_profile(self, profile: str) -> None:
        """Sätter aktuell agent profile"""
        self.current_profile = profile

    def get_profile(self) -> str:
        """Hämtar aktuell agent profile"""
        return self.current_profile

    async def check_connection(self) -> bool:
        """Verifierar att anslutningen faktiskt lever via en ping"""
        if not self.websocket or not self.connected:
            return False
        try:
            # Send ping and wait for pong
            pong_waiter = await self.websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=5)
            return True
        except Exception:
            self.connected = False
            return False
