"""
WebSocket client for Simons AI backend
Handles connection, streaming, and reconnect logic
"""
import asyncio
import json
from typing import AsyncGenerator, Optional
import websockets
from websockets.exceptions import (
    WebSocketException,
    ConnectionClosed,
    ConnectionClosedError,
    ConnectionClosedOK,
)

from .config import (
    get_backend_url,
    RECONNECT_DELAY,
    MAX_RECONNECT_ATTEMPTS,
    TIMEOUT,
    should_reconnect,
    MODEL_ARCHITECT,
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
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.url: str = get_backend_url()
        self.connected: bool = False
        self.current_mode: Optional[str] = None  # "juridik" or "diarie"
        self.current_profile: str = MODEL_ARCHITECT  # Default: gpt-oss
    
    async def connect(self) -> None:
        """Ansluter till backend med retry-logik"""
        attempt = 0

        while attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                # Use asyncio.wait_for for timeout compatibility across websockets versions
                # ping_timeout=None disables automatic ping which causes issues with slow AI responses
                self.websocket = await asyncio.wait_for(
                    websockets.connect(self.url, ping_timeout=None, close_timeout=10),
                    timeout=TIMEOUT
                )
                self.connected = True
                return

            except asyncio.TimeoutError:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    raise ConnectionError(f"Timeout efter {TIMEOUT} sekunder")
                await asyncio.sleep(RECONNECT_DELAY)
            except Exception as e:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    raise

                if should_reconnect(e):
                    await asyncio.sleep(RECONNECT_DELAY)
                else:
                    raise
    
    async def send_message(self, text: str, profile: Optional[str] = None) -> None:
        """Skickar meddelande till backend"""
        if not self.connected or not self.websocket:
            raise ConnectionError("Inte ansluten till backend")

        # Use current_profile if no profile specified
        active_profile = profile if profile else self.current_profile

        # Build message according to Antigravity protocol
        message = {
            "text": text,
            "profile": active_profile
        }
        
        try:
            await self.websocket.send(json.dumps(message))
        except (ConnectionClosed, ConnectionClosedError, ConnectionClosedOK) as e:
            self.connected = False
            raise ConnectionError(f"Anslutning stängd: {e}")
        except Exception as e:
            raise ConnectionError(f"Kunde inte skicka meddelande: {e}")
    
    async def receive_stream(self) -> AsyncGenerator[tuple[str, Optional[dict]], None]:
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
                    raise ConnectionError(f"Anslutning stängd: {e}")
                except json.JSONDecodeError:
                    # Skip invalid JSON
                    continue
            
            # Yield final stats if available
            if final_stats:
                yield ("", final_stats)
                    
        except websockets.exceptions.WebSocketException as e:
            self.connected = False
            raise ConnectionError(f"WebSocket-fel: {e}")
    
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
    
    def set_mode(self, mode: Optional[str]) -> None:
        """Sätter aktuellt läge (juridik/diarie)"""
        self.current_mode = mode

    def get_mode(self) -> Optional[str]:
        """Hämtar aktuellt läge"""
        return self.current_mode

    def set_profile(self, profile: str) -> None:
        """Sätter aktuell agent profile"""
        self.current_profile = profile

    def get_profile(self) -> str:
        """Hämtar aktuell agent profile"""
        return self.current_profile
