""".
SIMONS AI - COMMAND CENTER v3.0 (AUTO-SCROLL)
Dynamic Chat Rendering with Height-Aware Auto-Scroll.
GPT-OSS 20B (Arkitekt) + Devstral 24B (Kodare)
"""
import asyncio
import sys
import random
import time
import re
from datetime import datetime
from typing import List, Literal
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import box

# Import model config
from cli.config import (
    MODEL_ARCHITECT, MODEL_CODER,
    MODEL_ARCHITECT_NAME, MODEL_CODER_NAME
)

# Import client
try:
    from cli.client import NERDYAIClient
except ImportError:
    # Mock for standalone testing
    class NERDYAIClient:
        async def connect(self): pass
        async def send_message(self, text, profile): pass
        async def receive_stream(self):
            yield "Hello", None
            yield " World", {"speed": 99.9}
        async def close(self): pass
        def get_mode(self): return MODEL_ARCHITECT

# --- ASSETS & CONFIG ---

class Colors:
    # Command Center Palette
    PRIMARY = "bright_cyan"    # Default border / text
    ACTIVE = "bright_green"    # Success / Active Input
    WARNING = "gold1"          # Thinking / Processing
    ERROR = "red"              # Error
    DIM = "grey42"            # Inactive / Borders
    HIGHLIGHT = "white"        # Important text
    BACKGROUND = "black"

# The "Server Helmet" Avatar (Cyber-Visor)
AVATAR_IDLE = r"""
    ╒▅▀▀▀▀▀▅╕
    | ░░░░░ |
    | ▬   ▬ |
    | ░░░░░ |
    ╘▅▄▄▄▄▄▅╛
     //READY
"""

AVATAR_THINKING = r"""
    ╒▅▀▀▀▀▀▅╕
    | 1 0 1 |
    | 0 1 0 |
    | 1 0 1 |
    ╘▅▄▄▄▄▄▅╛
     //THINK
"""

AVATAR_SPEAKING = r"""
    ╒▅▀▀▀▀▀▅╕
    |  ▄ ▄  |
    | █▓█▓█ |
    |  ▀ ▀  |
    ╘▅▄▄▄▄▄▅╛
     //SPEAK
"""

# --- HELPER FUNCTIONS ---

def count_lines(text: str, width: int = 80) -> int:
    """Count how many terminal lines a text will occupy."""
    lines = text.split('\n')
    total = 0
    for line in lines:
        # Account for line wrapping
        if len(line) == 0:
            total += 1
        else:
            total += (len(line) // width) + 1
    return total


def format_ai_response(text: str) -> Text:
    """
    Parse and color-code Code Interpreter output.
    🔵 PLAN/TANKAR - Cyan
    🟠 KOD/HANDLING - Orange
    🟢 RESULTAT - Green
    🔴 ERROR - Red
    """
    formatted = Text()

    # Split into sections
    lines = text.split('\n')
    current_section = "normal"
    code_block = False

    for line in lines:
        # Detect code blocks
        if '```' in line:
            code_block = not code_block
            if code_block:
                formatted.append(line + '\n', style="orange1 bold")
            else:
                formatted.append(line + '\n', style="orange1")
            continue

        if code_block:
            # Inside code block - orange
            formatted.append(line + '\n', style="orange1")
            continue

        # Detect section headers
        line_lower = line.lower()

        if any(kw in line_lower for kw in ['uppgift:', 'plan:', 'tanke:', 'tänker:', 'analyserar:']):
            formatted.append(line + '\n', style="cyan bold")
        elif any(kw in line_lower for kw in ['kod:', 'script:', 'python:', 'executing:']):
            formatted.append(line + '\n', style="orange1 bold")
        elif any(kw in line_lower for kw in ['resultat:', 'output:', 'svar:', 'result:']):
            formatted.append(line + '\n', style="bright_green bold")
        elif any(kw in line_lower for kw in ['error:', 'fel:', 'traceback:', 'exception:']):
            formatted.append(line + '\n', style="red bold")
        elif line.startswith('>>>') or line.startswith('...'):
            # Python REPL output
            formatted.append(line + '\n', style="orange1")
        elif re.match(r'^\d+\.?\s', line):
            # Numbered list - likely plan
            formatted.append(line + '\n', style="cyan")
        else:
            formatted.append(line + '\n', style="white")

    return formatted


def render_chat_compact(messages: List[dict], available_height: int, chat_width: int = 80) -> Group:
    """
    Render chat messages with auto-scroll.
    Only shows messages that fit in available_height.
    Always shows the LATEST messages (auto-scroll to bottom).
    """
    # Calculate usable lines (minus header line)
    usable_lines = max(available_height - 2, 5)

    # Build visible messages from the end (newest first)
    lines_used = 0
    visible_items = []

    for msg in reversed(messages):
        role = msg["role"]
        text = msg["text"]

        # Calculate lines this message will take
        msg_lines = count_lines(text, chat_width) + 1  # +1 for role prefix

        if lines_used + msg_lines > usable_lines:
            # Can't fit more - but show partial if it's the latest
            if len(visible_items) == 0 and text:
                # Show as much as we can of the latest message
                lines_to_show = usable_lines - 1
                text_lines = text.split('\n')
                # Take last N lines that fit
                truncated_lines = text_lines[-(lines_to_show):]
                truncated_text = '\n'.join(truncated_lines)

                if role == "user":
                    item = Text()
                    item.append("▸ USER: ", style="cyan bold")
                    item.append(truncated_text, style="white")
                else:
                    item = Text()
                    item.append("◈ AI: ", style="bright_green bold")
                    item.append_text(format_ai_response(truncated_text))

                visible_items.insert(0, item)
            break

        # Format message
        if role == "user":
            item = Text()
            item.append("▸ USER: ", style="cyan bold")
            item.append(text, style="white")
        elif role == "system":
            item = Text()
            item.append("⚠ SYSTEM: ", style="yellow bold")
            item.append(text, style="yellow")
        else:
            item = Text()
            item.append("◈ AI: ", style="bright_green bold")
            item.append_text(format_ai_response(text))

        visible_items.insert(0, item)
        lines_used += msg_lines

    if not visible_items:
        return Group(Text("Awaiting Input...", style="dim"))

    return Group(*visible_items)


# --- STATE MANAGEMENT ---

@dataclass
class AppState:
    messages: List[dict] = field(default_factory=list)
    status: str = "STANDBY"
    connected: bool = False
    avatar_state: Literal["idle", "thinking", "speaking"] = "idle"
    current_agent: str = MODEL_ARCHITECT  # Active agent profile (sven-gpt default)

    # Telemetry Data
    core_temp: int = 42
    memory_usage: int = 12
    uplink_status: str = "ENCRYPTED"
    session_id: str = "992-ALPHA"

    def add_message(self, role: str, text: str):
        self.messages.append({"role": role, "text": text})
        if len(self.messages) > 50:
            self.messages = self.messages[-20:]

# --- LAYOUT GENERATOR ---

def get_avatar_art(state: AppState) -> str:
    if state.avatar_state == "thinking":
        return AVATAR_THINKING
    elif state.avatar_state == "speaking":
        return AVATAR_SPEAKING
    return AVATAR_IDLE

def get_border_color(state: AppState, zone: str) -> str:
    """State-Aware Borders"""
    if zone == "input":
        return Colors.PRIMARY
    
    if zone == "chat":
        if state.avatar_state == "thinking":
            return Colors.WARNING
        elif state.avatar_state == "speaking":
            return Colors.ACTIVE
        return Colors.DIM

    return Colors.DIM

def render_telemetry(state: AppState) -> Panel:
    """Right-side System Monitor"""
    # Simulate data fluctuation
    state.core_temp = random.randint(40, 65)
    state.memory_usage = random.randint(10, 45)

    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(style=Colors.DIM, width=12)
    grid.add_column(style=Colors.PRIMARY, justify="right")

    # Show active agent prominently
    is_coder = state.current_agent == MODEL_CODER
    agent_color = Colors.ACTIVE if is_coder else Colors.WARNING
    agent_display = MODEL_CODER_NAME if is_coder else MODEL_ARCHITECT_NAME
    grid.add_row("AGENT", f"[bold {agent_color}]{agent_display}[/]")
    grid.add_row("", "")  # Spacer

    grid.add_row("SESSION ID", state.session_id)
    grid.add_row("UPLINK", f"[{Colors.ACTIVE}]{state.uplink_status}[/]")
    grid.add_row("CORE TEMP", f"{state.core_temp}°C")
    grid.add_row("MEM BUFFER", f"{state.memory_usage}%")

    # Tips based on current agent
    tips_grid = Table.grid(expand=True)
    if is_coder:
        tips_grid.add_row(f"[bold green]CODE INTERPRETER[/]")
        tips_grid.add_row(f"[dim]Kan köra Python![/]")
    else:
        tips_grid.add_row(f"[bold yellow]TIP: /kod[/]")
        tips_grid.add_row(f"[dim]för Devstral[/]")

    return Panel(
        Group(grid, Text("\n"), tips_grid),
        title="[bold]SYSTEM MONITOR[/]",
        style=Colors.DIM,
        box=box.ROUNDED
    )

def make_layout(state: AppState, console_height: int = 40) -> Layout:
    """
    Create layout with dynamic chat height.
    console_height: Total terminal height (from console.size.height)
    """
    layout = Layout()

    # Header size for full avatar (7 lines + 2 borders)
    HEADER_SIZE = 9

    # Split: Header (Top), Middle (Chat+Stats)
    layout.split_column(
        Layout(name="header", size=HEADER_SIZE),
        Layout(name="middle")
    )

    layout["middle"].split_row(
        Layout(name="chat", ratio=8),  # More space for chat
        Layout(name="telemetry", ratio=2)  # Less for telemetry
    )

    # --- HEADER (Compact) ---
    avatar_text = Text(get_avatar_art(state), style=Colors.PRIMARY)
    status_color = Colors.ACTIVE if state.connected else Colors.ERROR
    status_text = "ONLINE" if state.connected else "OFFLINE"

    # Show proper display name
    is_coder = state.current_agent == MODEL_CODER
    agent_display = MODEL_CODER_NAME if is_coder else MODEL_ARCHITECT_NAME

    # Code Interpreter indicator for coder
    ci_badge = ""
    if is_coder:
        ci_badge = " [bold green]⚡CI[/]"

    layout["header"].update(Panel(
        Align.center(avatar_text),
        title=f"[{status_color}]● {status_text}[/] | [bold cyan]{agent_display}[/]{ci_badge}",
        subtitle="[dim]SIMONS AI v3.0 | /help | /kod[/]",
        style=Colors.DIM,
        box=box.ROUNDED,
        padding=(0, 1)
    ))

    # --- CHAT (Dynamic Height Auto-Scroll) ---
    # Calculate available height for chat panel
    # Total height - header - input line - panel borders
    chat_height = console_height - HEADER_SIZE - 3

    # Get terminal width for chat (80% of total for chat panel)
    chat_width = 70  # Approximate

    chat_border = get_border_color(state, "chat")
    chat_title = "CHAT LOG"
    if state.avatar_state == "thinking":
        chat_title = "⏳ PROCESSING..."
    elif state.avatar_state == "speaking":
        chat_title = "📡 INCOMING..."

    # Use compact rendering with auto-scroll
    chat_content = render_chat_compact(state.messages, chat_height, chat_width)

    layout["chat"].update(Panel(
        chat_content,
        title=f"[{chat_border}]{chat_title}[/]",
        style=chat_border,
        box=box.ROUNDED,
        padding=(0, 1)
    ))

    # --- TELEMETRY ---
    layout["telemetry"].update(render_telemetry(state))

    return layout

# --- MAIN APPLICATION ---

async def main():
    console = Console()
    state = AppState()
    client = NERDYAIClient()

    # Connect
    try:
        await client.connect()
        state.connected = True
        state.status = "ONLINE"
    except:
        state.status = "OFFLINE"

    while True:
        try:
            # Sync agent state with client
            state.current_agent = client.get_profile()

            # Get terminal dimensions for dynamic layout
            term_height = console.size.height
            term_width = console.size.width

            # 1. Render Static Interface (Idle State)
            console.clear()
            state.avatar_state = "idle"
            console.print(make_layout(state, term_height))

            # 2. Safe Input (Blocking)
            user_input = console.input(f"[{Colors.PRIMARY}]❯[/] ").strip()

            if not user_input:
                continue

            # Handle slash commands
            if user_input.startswith("/"):
                from cli.commands import handle_slash_command
                should_exit = await handle_slash_command(client, user_input)
                if should_exit:
                    break
                continue

            state.add_message("user", user_input)

            # 3. Live Thinking/Streaming State
            state.avatar_state = "thinking"

            # We use Live context only during active processing/streaming
            with Live(make_layout(state, term_height), console=console, screen=True, refresh_per_second=12) as live:

                await asyncio.sleep(0.2)

                try:
                    await client.send_message(user_input)

                    state.avatar_state = "speaking"
                    state.add_message("ai", "")

                    async for token, stats in client.receive_stream():
                        if token:
                            state.messages[-1]["text"] += token
                            # Update with current terminal height
                            live.update(make_layout(state, console.size.height))

                    state.avatar_state = "idle"
                    await asyncio.sleep(0.3)

                except Exception as e:
                    state.add_message("system", f"Error: {e}")
                    state.avatar_state = "idle"
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Critical Error: {e}[/]")
            break

    await client.close()
    console.print("[dim]Session Terminated.[/]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
