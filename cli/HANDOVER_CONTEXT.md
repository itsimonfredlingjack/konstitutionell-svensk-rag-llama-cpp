# NERDY AI CLI - Teknisk Överlämning (Handover Document)

## 1. Filstruktur

```
/home/dev/ai-server/cli/
├── __init__.py          # Package initialization
├── main.py              # Main entry point and REPL loop
├── client.py            # WebSocket client and backend communication
├── ui.py                # Rich UI components (banners, panels, streaming)
├── commands.py          # Slash command handlers (/juridik, /diarie, /clear, /quit)
├── config.py            # Configuration (backend URL, reconnect logic)
└── requirements.txt     # Dependencies: rich>=13.0.0, websockets>=12.0
```

## 2. Källkod - Frontend (main.py)

```python
"""
NERDY AI CLI - Main entry point
Cyberpunk Legal Console - Interactive REPL
"""
import asyncio
import sys
import os
from pathlib import Path
from rich.prompt import Prompt
from rich.console import Console

# Support both running as script and as module
if __name__ == "__main__" and __package__ is None:
    # Running as script: add parent directory to path
    cli_dir = Path(__file__).parent
    ai_server_dir = cli_dir.parent
    sys.path.insert(0, str(ai_server_dir))
    from cli.client import NERDYAIClient
    from cli.ui import (
        render_welcome_banner,
        show_thinking_spinner,
        show_status,
        print_separator,
        render_metadata_footer,
        get_user_prompt,
        render_agent_header,
        render_status_bar,
        create_streaming_display,
        update_streaming_display,
    )
    from cli.commands import handle_slash_command
else:
    # Running as module
    from .client import NERDYAIClient
    from .ui import (
        render_welcome_banner,
        show_thinking_spinner,
        show_status,
        print_separator,
        render_metadata_footer,
        get_user_prompt,
        render_agent_header,
        render_status_bar,
        create_streaming_display,
        update_streaming_display,
    )
    from .commands import handle_slash_command

console = Console()


async def get_user_input() -> str:
    """
    Simple user input with clean prompt
    """
    try:
        # Print simple prompt
        prompt_text = get_user_prompt()
        console.print(prompt_text, end="")
        
        # Force flush to ensure prompt is visible
        import sys
        sys.stdout.flush()
        
        # Get input
        user_input = input()
        
        # Handle empty input
        if not user_input.strip():
            return ""
        
        return user_input.strip()
    except (EOFError, KeyboardInterrupt):
        return "/quit"


async def main():
    """
    Main REPL loop with cyberpunk aesthetics
    """
    # Show welcome dashboard
    render_welcome_banner()
    
    # Show status bar
    render_status_bar()
    
    # Create client
    client = NERDYAIClient()
    
    try:
        # Connect to backend
        try:
            await client.connect()
        except ConnectionError as e:
            show_status(f"Connection failed: {e}", "error")
            show_status("Verify backend is running on ws://localhost:8000/api/chat", "info")
            sys.exit(1)
        
        # REPL loop
        while True:
            try:
                # Get user input
                user_input = await get_user_input()
                
                # Skip empty input
                if not user_input:
                    continue
                
                # Handle slash commands
                if user_input.startswith("/"):
                    should_exit = await handle_slash_command(client, user_input)
                    if should_exit:
                        break
                    continue
                
                # Send message to backend
                try:
                    await client.send_message(user_input, profile="nerdy")
                except ConnectionError as e:
                    show_status(f"Connection error: {e}", "error")
                    show_status("Attempting reconnect...", "warning")
                    try:
                        await client.connect()
                        # Retry sending message after reconnect
                        await client.send_message(user_input, profile="nerdy")
                    except Exception as reconnect_error:
                        show_status(f"Reconnect failed: {reconnect_error}", "error")
                        break
                
                # Render agent header with styling
                render_agent_header()
                
                # Create Live display for streaming
                live, accumulated_text = create_streaming_display()
                final_stats = None
                
                try:
                    # Start Live context for smooth streaming
                    with live:
                        # Iterate over chunks and accumulate text
                        async for token, stats in client.receive_stream():
                            if stats:
                                # Final stats received
                                final_stats = stats
                                break
                            if token:
                                # Update Live display with new token
                                # This accumulates text and updates Markdown
                                update_streaming_display(live, accumulated_text, token)
                    
                    # Live context ends here, final state is displayed
                    console.print()  # Blank line after response
                    
                    # Show metadata footer as Rule
                    if final_stats:
                        render_metadata_footer(final_stats)
                    else:
                        # Show footer even without stats (with mock data)
                        render_metadata_footer()
                    
                except ConnectionError as e:
                    show_status(f"Connection lost during streaming: {e}", "error")
                    show_status("Attempting reconnect...", "warning")
                    try:
                        await client.connect()
                    except Exception as reconnect_error:
                        show_status(f"Reconnect failed: {reconnect_error}", "error")
                        break
                
            except KeyboardInterrupt:
                # Ctrl+C - graceful exit
                console.print("\n")
                await handle_slash_command(client, "/quit")
                break
            except Exception as e:
                show_status(f"Unexpected error: {e}", "error")
                # Continue loop despite errors
                continue
                
    except KeyboardInterrupt:
        console.print("\n")
        await handle_slash_command(client, "/quit")
    except Exception as e:
        show_status(f"Critical error: {e}", "error")
        sys.exit(1)
    finally:
        # Close connection gracefully
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold bright_cyan]Session terminated. Thank you for using NERDY AI![/]")
        sys.exit(0)
```

## 3. Källkod - Client Logic (client.py)

```python
"""
WebSocket client for NERDY AI backend
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
)
from .ui import show_status


class NERDYAIClient:
    """
    WebSocket client för NERDY AI backend.
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
    
    async def connect(self) -> None:
        """Ansluter till backend med retry-logik"""
        attempt = 0
        
        while attempt < MAX_RECONNECT_ATTEMPTS:
            try:
                show_status(f"Ansluter till backend... (försök {attempt + 1}/{MAX_RECONNECT_ATTEMPTS})", "info")
                
                # Use asyncio.wait_for for timeout compatibility across websockets versions
                self.websocket = await asyncio.wait_for(
                    websockets.connect(self.url),
                    timeout=TIMEOUT
                )
                self.connected = True
                show_status("Ansluten till NERDY AI backend", "success")
                return
                
            except asyncio.TimeoutError:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    show_status(f"Timeout: Kunde inte ansluta efter {TIMEOUT} sekunder", "error")
                    raise ConnectionError(f"Timeout efter {TIMEOUT} sekunder")
                show_status(f"Timeout - försöker igen om {RECONNECT_DELAY} sekunder...", "warning")
                await asyncio.sleep(RECONNECT_DELAY)
            except Exception as e:
                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    show_status(f"Kunde inte ansluta efter {MAX_RECONNECT_ATTEMPTS} försök: {e}", "error")
                    raise
                
                if should_reconnect(e):
                    show_status(f"Försöker återansluta om {RECONNECT_DELAY} sekunder...", "warning")
                    await asyncio.sleep(RECONNECT_DELAY)
                else:
                    show_status(f"Anslutningsfel: {e}", "error")
                    raise
    
    async def send_message(self, text: str, profile: str = "nerdy") -> None:
        """Skickar meddelande till backend"""
        if not self.connected or not self.websocket:
            raise ConnectionError("Inte ansluten till backend")
        
        # Build message according to Antigravity protocol
        message = {
            "text": text,
            "profile": profile
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
```

## 4. Backend Interface

### WebSocket Endpoint
- **URL:** `ws://localhost:8000/api/chat`
- **Protocol:** Antigravity format (legacy simple format)

### Incoming Message Format (Client → Backend)
```json
{
  "text": "user message",
  "profile": "nerdy"
}
```

### Outgoing Message Format (Backend → Client)

**Streaming tokens (during response):**
```json
{
  "sender": "agent",
  "text": "token...",
  "is_finished": false,
  "agent_id": "nerdy",
  "model": "qwen2.5-coder:14b",
  "provider": "ollama"
}
```

**Final message (completion):**
```json
{
  "sender": "agent",
  "text": "",
  "is_finished": true,
  "model": "qwen2.5-coder:14b",
  "provider": "ollama",
  "agent_id": "nerdy",
  "stats": {
    "tokens": 714,
    "speed": 39.2,
    "duration_ms": 18200,
    "provider": "ollama",
    "model": "qwen2.5-coder:14b",
    "agent_id": "nerdy"
  }
}
```

**Notes:**
- Tokens are sent as **text chunks** (strings), not JSON objects
- Each token is a small piece of the response (could be a word, part of a word, or punctuation)
- `is_finished: false` for all streaming tokens
- `is_finished: true` only in the final message
- Stats are only included in the final message
- Backend uses `stats.tokens` and `stats.speed` (tokens per second)

## 5. Design Brief & Buggar

### Mål: Cyberpunk/Sci-Fi Terminal Look
- **Dashboard:** Sammanhållen två-kolumns layout i en enda Panel (fungerar bra nu)
- **Chat:** Snyggt formatterad med färger, tydlig separation mellan användare och AI
- **Streaming:** Live text som flödar in smidigt med syntax highlighting
- **Metadata:** Diskret Rule med stats efter varje svar

### Kända Problem (Kritiska Buggar)

#### 1. "Scenskräck" - Streaming Buggen
**Symptom:**
- Texten försvinner eller klipps av ("testo", "g", "te...")
- Ibland syns bara första bokstaven, sen inget mer
- AI:ns svar renderas inte korrekt

**Nuvarande Implementation:**
- Använder `rich.live.Live` med `Markdown`-objekt
- `create_streaming_display()` skapar Live context
- `update_streaming_display()` ackumulerar text och uppdaterar Markdown
- Problem: Markdown-objektet uppdateras men texten syns inte eller försvinner

**Trolig orsak:**
- Live context uppdateras för snabbt eller krockar med console output
- Markdown-objektet renderas inte korrekt i Live context
- Panel med MINIMAL box kan dölja texten

#### 2. Design - För platt/tråkig chat
**Symptom:**
- Chatten ser ut som vanlig text (vit på svart)
- Ingen visuell struktur eller färgkodning i själva chat-meddelandena
- Användarens input och AI:ns svar ser likadana ut

**Nuvarande Implementation:**
- User prompt: `[bold cyan]👤 USER[/] [dim]@[/] [cyan]CASE-FILE[/] [bold bright_white]❯[/]`
- AI header: `[bold magenta]🤖 NERDY AI[/] [dim]processing...[/]`
- AI response: I Panel med MINIMAL box, bright_white text
- Problem: Texten i Panel syns inte eller är för diskret

#### 3. Layout - Separata boxar
**Status:** ✅ FIXAT - Dashboarden använder nu Table.grid inuti en enda Panel

### Önskad Lösning

1. **Streaming:**
   - Text ska synas direkt när den kommer från backend
   - Hela svaret ska renderas, inte bara första bokstaven
   - Använd Rich-komponenter för snygg formatering (Markdown, syntax highlighting)
   - Inga blinkningar eller försvinnande text

2. **Design:**
   - Tydlig visuell separation: Användare (cyan) vs AI (magenta)
   - Färgkodad text i AI-svaren (inte bara vit)
   - Struktur utan tunga boxar (använd Padding, MINIMAL borders)
   - Cyberpunk-känsla med neon-färger

3. **Metadata:**
   - Diskret Rule med stats (fungerar bra nu)
   - Tydlig avdelare mellan interaktioner

### Tekniska Krav

- **Bibliotek:** `rich` (>=13.0.0) - använd Rich-komponenter, inte vanlig print()
- **Streaming:** Måste fungera med `rich.live.Live` eller alternativ metod
- **Färger:** Använd Rich's färgsystem (bright_cyan, bright_magenta, etc.)
- **Struktur:** Använd Panel, Padding, Markdown för formatering
- **Performance:** Streaming måste vara smidig, ingen lagg eller blinkning

### Test-scenario

1. Starta CLI: `python3 -m cli.main`
2. Skriv: `test`
3. Förväntat resultat:
   - AI:ns svar ska streamas in tecken för tecken
   - Hela svaret ska synas (inte bara "t" eller "te")
   - Text ska vara färgkodad och snyggt formaterad
   - Metadata ska visas som Rule efter svaret

---

**Sammanfattning för Gemini:**
"Fix streaming-buggen där texten försvinner. Gör chatten snyggt formatterad med Rich-komponenter. Behåll dashboarden i toppen (den fungerar bra). Använd färger, struktur och tydlig separation mellan användare och AI. Målet är en Cyberpunk-terminal som känns proffsig och fungerar."
