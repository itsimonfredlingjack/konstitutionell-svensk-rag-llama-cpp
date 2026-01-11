"""
THE OPUS TERMINAL - SIMONS AI v4.0
===================================
SOUL INJECTION Edition - Robot Avatar + Cyberpunk Dashboard
Built with Textual TUI by Will McGugan
"""

import random
from typing import ClassVar

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Input, RichLog, Static

# ═══════════════════════════════════════════════════════════════════════════════
# ROBOT AVATAR - THE SOUL
# ═══════════════════════════════════════════════════════════════════════════════

AVATARS = {
    "idle": """
    ╒▅▀▀▀▀▀▅╕
    | ░░░░░ |
    | ▬   ▬ |
    | ░░░░░ |
    ╘▅▄▄▄▄▄▅╛
     //READY
""",
    "thinking": """
    ╒▅▀▀▀▀▀▅╕
    | 1 0 1 |
    | 0 1 0 |
    | 1 0 1 |
    ╘▅▄▄▄▄▄▅╛
     //THINK
""",
    "speaking": """
    ╒▅▀▀▀▀▀▅╕
    |  ▄ ▄  |
    | █▓█▓█ |
    |  ▀ ▀  |
    ╘▅▄▄▄▄▄▅╛
     //SPEAK
""",
    "error": """
    ╒▅▀▀▀▀▀▅╕
    | X   X |
    |  ▄▄▄  |
    | ~~~~~ |
    ╘▅▄▄▄▄▄▅╛
     //ERROR
""",
}

# State colors (vibe-coding approved)
STATE_COLORS = {
    "idle": "#00F3FF",  # Neon Cyan
    "thinking": "#FFB74D",  # Amber
    "speaking": "#00FF41",  # Neon Green
    "error": "#FF00FF",  # Magenta
}

# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CONFIGURATIONS - Matches Backend_Fraga_Router.py
# ═══════════════════════════════════════════════════════════════════════════════

AGENTS = {
    "gpt-oss": {
        "name": "GPT-OSS 20B",
        "description": "Arkitekten",
        "color": "#7A00FF",
        "icon": "🧠",
        "code_interpreter": False,
    },
    "devstral": {
        "name": "Devstral 24B",
        "description": "Kodaren",
        "color": "#00FF41",
        "icon": "⚡",
        "code_interpreter": True,
    },
}

# Agent cycle order
AGENT_CYCLE = ["gpt-oss", "devstral"]


class RobotHeader(Static):
    """The Robot Avatar with status - THE SOUL of the terminal."""

    state = reactive("idle")
    status_text = reactive("CONNECTING...")

    def render(self):
        color = STATE_COLORS.get(self.state, "#00F3FF")
        avatar = AVATARS.get(self.state, AVATARS["idle"])

        # Build avatar with color
        avatar_styled = Text(avatar, style=color)

        # Status badge
        if self.state == "idle":
            status = Text("● ONLINE", style="bold #00FF41")
        elif self.state == "thinking":
            status = Text("◐ THINKING...", style="bold #FFB74D")
        elif self.state == "speaking":
            status = Text("◉ STREAMING", style="bold #00FF41")
        else:
            status = Text("✗ ERROR", style="bold #FF00FF")

        # Title text
        title = Text("\n  SIMONS AI v4.0  ", style="bold #E0F7FA")
        title.append(status)

        # Combine avatar and title side by side
        return Group(Align.center(avatar_styled), Align.center(title))


class SystemMonitor(Static):
    """Telemetry panel - Agent status, GPU stats, Code Interpreter badge."""

    agent = reactive("sven-gpt")
    state = reactive("idle")

    def render(self):
        # Get agent config
        agent_cfg = AGENTS.get(self.agent, AGENTS["sven-gpt"])
        agent_display = agent_cfg["name"]
        agent_color = agent_cfg["color"]
        agent_desc = agent_cfg["description"]
        agent_icon = agent_cfg["icon"]
        code_interpreter = agent_cfg["code_interpreter"]

        # Status with appropriate color
        status_color = STATE_COLORS.get(self.state, "#64748B")
        status_map = {
            "idle": "IDLE",
            "thinking": "PROCESSING",
            "speaking": "STREAMING",
            "error": "ERROR",
        }
        status = status_map.get(self.state, "UNKNOWN")

        # Simulated GPU stats (could be real via nvidia-smi)
        temp = random.randint(42, 58)
        vram = f"{random.uniform(8.5, 10.5):.1f}"

        # Code Interpreter badge
        ci_badge = "[bold #00FF41]ON [/]" if code_interpreter else "[dim]OFF[/]"

        content = Text()
        content.append("─── AGENT ───\n", style="dim #94A3B8")
        content.append(f"  {agent_icon} {agent_display}\n", style=f"bold {agent_color}")
        content.append(f"    {agent_desc}\n", style="dim #94A3B8")
        content.append("\n")
        content.append("─── STATUS ───\n", style="dim #94A3B8")
        content.append(f"  {status}\n", style=f"bold {status_color}")
        content.append("\n")
        content.append("─── GPU ───\n", style="dim #94A3B8")
        content.append(f"  TEMP: {temp}°C\n", style="#E0F7FA")
        content.append(f"  VRAM: {vram}GB\n", style="#E0F7FA")
        content.append("\n")
        content.append("─── TOOLS ───\n", style="dim #94A3B8")
        content.append("  🔧 CODE INTERP: ", style="#E0F7FA")
        content.append_text(Text.from_markup(ci_badge))

        return Panel(
            content, title="[bold #FFAE00]SYSTEM MONITOR[/]", border_style="#FFAE00", padding=(0, 1)
        )


class SimonsAIApp(App):
    """THE OPUS TERMINAL - AI Command Center."""

    # ═══════════════════════════════════════════════════════════════════════════
    # CYBERPUNK CSS - Vibe Coding Approved
    # ═══════════════════════════════════════════════════════════════════════════

    CSS = """
    Screen {
        background: #0D1117;
    }

    #robot-header {
        height: 10;
        background: #0D1117;
        border-bottom: solid #00F3FF;
    }

    #main-area {
        height: 1fr;
    }

    #chat {
        width: 70%;
        background: #1A1B26;
        border: solid #00F3FF;
        border-title-color: #00F3FF;
        padding: 0 1;
        scrollbar-background: #1A1B26;
        scrollbar-color: #00F3FF;
        scrollbar-color-hover: #00FF41;
    }

    #chat.thinking {
        border: solid #FFB74D;
    }

    #chat.speaking {
        border: solid #00FF41;
    }

    #system-monitor {
        width: 30%;
        background: #1A1B26;
        padding: 0;
    }

    Input {
        dock: bottom;
        height: 3;
        background: #1A1B26;
        border: solid #00F3FF;
        color: #E0F7FA;
    }

    Input:focus {
        border: solid #00FF41;
    }

    Input > .input--placeholder {
        color: #64748B;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("ctrl+a", "toggle_agent", "Agent", show=True),
        Binding("escape", "focus_input", "Focus", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.client = None
        self.current_response = ""

    def compose(self) -> ComposeResult:
        """Build the dashboard layout."""
        # TOP: Robot Header
        yield RobotHeader(id="robot-header")

        # MIDDLE: Chat + System Monitor (70/30 split)
        with Horizontal(id="main-area"):
            yield RichLog(id="chat", markup=True, highlight=True, wrap=True)
            yield SystemMonitor(id="system-monitor")

        # BOTTOM: Input
        yield Input(id="input", placeholder="Skriv kommando... (/help för hjälp)")

    async def on_mount(self):
        """Initialize on startup."""
        from cli.client import NERDYAIClient

        self.client = NERDYAIClient()
        robot = self.query_one("#robot-header", RobotHeader)
        log = self.query_one("#chat", RichLog)
        monitor = self.query_one("#system-monitor", SystemMonitor)

        # Welcome banner
        log.write(
            Text.from_markup("[dim]════════════════════════════════════════════════════════════[/]")
        )
        log.write(Text.from_markup("[bold #00F3FF]       ╒▅▀▀▀▀▀▅╕  THE OPUS TERMINAL[/]"))
        log.write(Text.from_markup("[bold #00F3FF]       | ▬   ▬ |  SIMONS AI v4.0[/]"))
        log.write(Text.from_markup("[bold #00F3FF]       ╘▅▄▄▄▄▄▅╛  Textual + Robot Soul[/]"))
        log.write(
            Text.from_markup("[dim]════════════════════════════════════════════════════════════[/]")
        )
        log.write("")

        # Connect to backend
        try:
            await self.client.connect()
            robot.state = "idle"
            robot.status_text = "ONLINE"
            monitor.agent = self.client.get_profile()
            log.write(Text.from_markup("[bold #00FF41]✓ Connected to backend[/]"))
        except Exception as e:
            robot.state = "error"
            robot.status_text = "OFFLINE"
            log.write(Text.from_markup(f"[bold #FF00FF]✗ Connection failed: {e}[/]"))

        log.write("")

        # Focus input
        self.query_one("#input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted):
        """Handle Enter key."""
        user_text = event.value.strip()
        if not user_text:
            return

        event.input.value = ""

        # Slash commands
        if user_text.startswith("/"):
            await self.handle_command(user_text)
            return

        # User message
        log = self.query_one("#chat", RichLog)
        log.write(Text.from_markup(f"[bold #00F3FF]USER ▸[/] {user_text}"))

        # Send to AI
        self.send_to_ai(user_text)

    @work(exclusive=True)
    async def send_to_ai(self, text: str):
        """Background worker for AI communication."""
        log = self.query_one("#chat", RichLog)
        robot = self.query_one("#robot-header", RobotHeader)
        monitor = self.query_one("#system-monitor", SystemMonitor)
        chat_widget = self.query_one("#chat")

        if not self.client or not self.client.connected:
            log.write(Text.from_markup("[bold #FF00FF]Not connected![/]"))
            return

        # THINKING state
        robot.state = "thinking"
        monitor.state = "thinking"
        chat_widget.add_class("thinking")
        chat_widget.remove_class("speaking")

        try:
            await self.client.send_message(text)

            # SPEAKING state
            robot.state = "speaking"
            monitor.state = "speaking"
            chat_widget.remove_class("thinking")
            chat_widget.add_class("speaking")

            # AI prefix
            log.write(Text.from_markup("[bold #00FF41]AI ▸[/] "), end="")

            self.current_response = ""
            async for token, _stats in self.client.receive_stream():
                if token:
                    self.current_response += token
                    log.write(token, end="")

            log.write("")  # Newline

            # Back to IDLE
            robot.state = "idle"
            monitor.state = "idle"
            chat_widget.remove_class("thinking")
            chat_widget.remove_class("speaking")

        except Exception as e:
            robot.state = "error"
            monitor.state = "error"
            log.write(Text.from_markup(f"\n[bold #FF00FF]ERROR: {e}[/]"))

    async def handle_command(self, cmd: str):
        """Slash commands."""
        log = self.query_one("#chat", RichLog)
        monitor = self.query_one("#system-monitor", SystemMonitor)
        parts = cmd.split()
        command = parts[0].lower()

        if command == "/help":
            log.write(Text.from_markup("[dim]═══════════════════ COMMANDS ═══════════════════[/]"))
            log.write(Text.from_markup("[#00F3FF]/help[/]    - Visa denna hjälp"))
            log.write(Text.from_markup("[#00F3FF]/clear[/]   - Rensa chatten"))
            log.write(Text.from_markup("[#7A00FF]/sven[/]    - 🧠 Arkitekten (planering)"))
            log.write(Text.from_markup("[#00FF41]/kod[/]     - ⚡ Kodaren (implementation)"))
            log.write(Text.from_markup("[#00F3FF]/status[/]  - Visa status"))
            log.write(Text.from_markup("[#00F3FF]/quit[/]    - Avsluta"))
            log.write(Text.from_markup("[dim]═══════════════════ SHORTCUTS ══════════════════[/]"))
            log.write(Text.from_markup("[#00F3FF]Ctrl+C[/]   - Quit"))
            log.write(Text.from_markup("[#00F3FF]Ctrl+L[/]   - Clear"))
            log.write(Text.from_markup("[#00F3FF]Ctrl+A[/]   - Växla Agent (cykel)"))
            log.write(Text.from_markup("[dim]════════════════════════════════════════════════[/]"))

        elif command == "/clear":
            log.clear()
            log.write(Text.from_markup("[dim]Chat cleared[/]"))

        elif command in ["/sven", "/gpt", "/arkitekt"]:
            self._switch_agent("gpt-oss", log, monitor)

        elif command in ["/kod", "/coder", "/dev"]:
            self._switch_agent("devstral", log, monitor)

        elif command == "/status":
            connected = self.client.connected if self.client else False
            agent_id = self.client.get_profile() if self.client else "unknown"
            agent_cfg = AGENTS.get(agent_id, AGENTS["gpt-oss"])
            status_color = "#00FF41" if connected else "#FF00FF"
            status_text = "ONLINE" if connected else "OFFLINE"
            log.write(Text.from_markup(f"[dim]Connection:[/] [{status_color}]{status_text}[/]"))
            log.write(
                Text.from_markup(
                    f"[dim]Agent:[/] [{agent_cfg['color']}]{agent_cfg['icon']} {agent_cfg['name']}[/]"
                )
            )
            log.write(Text.from_markup("[dim]Backend:[/] ws://localhost:8000/api/chat"))

        elif command in ["/quit", "/exit", "/q"]:
            self.exit()

        else:
            log.write(Text.from_markup(f"[#FFB74D]Okänt kommando: {command}. Prova /help[/]"))

    def _switch_agent(self, agent_id: str, log: RichLog, monitor: SystemMonitor):
        """Helper to switch agent."""
        if self.client:
            self.client.set_profile(agent_id)
            monitor.agent = agent_id
            agent_cfg = AGENTS[agent_id]
            log.write(
                Text.from_markup(
                    f"[{agent_cfg['color']}]{agent_cfg['icon']} Switched to {agent_cfg['name']}[/]"
                )
            )
            if agent_cfg["code_interpreter"]:
                log.write(Text.from_markup("[bold #00FF41]   🔧 Code Interpreter ACTIVE[/]"))

    def action_clear_chat(self):
        """Ctrl+L."""
        self.query_one("#chat", RichLog).clear()

    def action_toggle_agent(self):
        """Ctrl+A - Cycle through all agents."""
        monitor = self.query_one("#system-monitor", SystemMonitor)
        log = self.query_one("#chat", RichLog)

        if self.client:
            # Find current index and get next
            current = monitor.agent
            try:
                idx = AGENT_CYCLE.index(current)
                next_idx = (idx + 1) % len(AGENT_CYCLE)
            except ValueError:
                next_idx = 0

            next_agent = AGENT_CYCLE[next_idx]
            self._switch_agent(next_agent, log, monitor)

    def action_focus_input(self):
        """Escape."""
        self.query_one("#input", Input).focus()

    async def on_unmount(self):
        """Cleanup."""
        if self.client:
            await self.client.close()


def main():
    """Entry point."""
    app = SimonsAIApp()
    app.run()


if __name__ == "__main__":
    main()
