from __future__ import annotations

from datetime import datetime

import pygments.styles
from rich.align import Align
from rich.columns import Columns
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from .theme import COLORS

# Register custom syntax themes
pygments.styles.STYLE_MAP["rag_neon"] = "rag_cli.ui.theme:RagNeonStyle"
pygments.styles.STYLE_MAP["rag_terminal"] = "rag_cli.ui.theme:RagTerminalStyle"

# Spinner frames for processing state
SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]

# Display-state translation map (internal state → Swedish label)
_STATE_LABELS = {
    "IDLE": "REDO",
    "PROCESSING": "SÖKER...",
    "INPUT": "INPUT",
    "ERROR": "FEL",
    "READY": "REDO",
}


def _score_bar(score: float, width: int = 5) -> str:
    """Return a block bar like ▓▓▓▓░ proportional to score (0–1)."""
    filled = round(score * width)
    return "▓" * filled + "░" * (width - filled)


class HeaderBar(Widget):
    """Full-width header with logo, status, and connection info."""

    status = reactive("READY")
    model = reactive("mistral-nemo")
    branch = reactive("master")
    backend_url = reactive("localhost:8900")
    backend_online = reactive(True)

    def render(self) -> RenderableType:
        c = COLORS
        # Status badge (center)
        st = self.status
        label = _STATE_LABELS.get(st, st)
        if st == "PROCESSING":
            badge_style = c["secondary"]
            badge_icon = "◐"
        elif st == "INPUT":
            badge_style = c["primary"]
            badge_icon = "●"
        elif st == "ERROR":
            badge_style = c["error"]
            badge_icon = "●"
        else:
            badge_style = c["text_dim"]
            badge_icon = "●"

        # Connection info (right)
        online_text = "ONLINE" if self.backend_online else "OFFLINE"

        width = self.size.width - 4
        mid = width // 2
        right_col = width - mid

        line1 = Text()
        line1.append(" ▟█▙  ", style=f"bold {c['primary']}")
        line1.append("RAG CLI", style=f"bold {c['text_bright']}")

        status1 = Text()
        status1.append(f"{badge_icon} {label}", style=badge_style)

        conn1 = Text()
        conn1.append(f"{self.branch}", style=c["text_dim"])
        conn1.append(" · ", style=c["text_dim"])
        conn1.append(f"{self.model}", style=c["secondary"])

        line2 = Text()
        line2.append(" ▜█▛  ", style=f"bold {c['primary']}")
        line2.append("v0.6.0", style=c["text_dim"])

        conn2 = Text()
        conn2.append(f"{self.backend_url} ", style=c["text_dim"])
        conn2.append("● ", style=c["success"] if self.backend_online else c["error"])
        conn2.append(online_text, style=c["success"] if self.backend_online else c["error"])

        # Build each line with proper alignment
        result = Text()

        # Line 1: logo ... status ... connection
        pad1_left = max(1, mid - len(line1) - len(status1) // 2)
        pad1_right = max(1, right_col - len(status1) // 2 - len(conn1))
        result.append_text(line1)
        result.append(" " * pad1_left)
        result.append_text(status1)
        result.append(" " * pad1_right)
        result.append_text(conn1)
        result.append("\n")

        # Line 2: version ... spacer ... connection2
        pad2 = max(1, width - len(line2) - len(conn2))
        result.append_text(line2)
        result.append(" " * pad2)
        result.append_text(conn2)

        return result


class StatusPanel(Widget):
    """Sidebar panel showing current state, mode, and backend status."""

    state = reactive("IDLE")
    mode = reactive("auto")
    backend_online = reactive(True)
    last_query = reactive("")

    def render(self) -> RenderableType:
        c = COLORS
        st = self.state
        label = _STATE_LABELS.get(st, st)
        if st == "PROCESSING":
            state_style = c["secondary"]
        elif st == "INPUT":
            state_style = c["primary"]
        elif st == "ERROR":
            state_style = c["error"]
        else:
            state_style = c["text_dim"]

        online_style = c["success"] if self.backend_online else c["error"]
        online_text = "● ansluten" if self.backend_online else "● frånkopplad"

        t = Text()
        t.append("\n")
        t.append("  Läge:    ", style=c["sidebar_text_dim"])
        t.append(f"{label}\n", style=state_style)
        t.append("  Sökläge: ", style=c["sidebar_text_dim"])
        t.append(f"{self.mode}\n", style=c["sidebar_text"])
        t.append("  Server:  ", style=c["sidebar_text_dim"])
        t.append(f"{online_text}\n", style=online_style)
        if self.last_query:
            truncated = self.last_query[:18] + "…" if len(self.last_query) > 18 else self.last_query
            t.append("  Senaste: ", style=c["sidebar_text_dim"])
            t.append(f"{truncated}\n", style=c["sidebar_text"])
        return t


class SourcesPanel(Widget):
    """Sidebar panel showing scored source references."""

    sources: reactive[list[dict]] = reactive(list, always_update=True)

    def render(self) -> RenderableType:
        c = COLORS
        t = Text()
        t.append("\n")
        if not self.sources:
            t.append("  Inga källor ännu.\n", style=c["sidebar_text_dim"])
        else:
            for src in self.sources[:6]:
                score = src.get("score", 0)
                title = src.get("title", "Unknown")
                # Truncate long titles
                if len(title) > 18:
                    title = title[:17] + "…"
                bar = _score_bar(score)
                t.append(f"  {bar} ", style=c["primary"])
                t.append(f"{title}\n", style=c["sidebar_text"])
        return t


class MetadataPanel(Widget):
    """Sidebar panel showing hits, tokens, latency, evidence."""

    hits = reactive("--")
    tokens = reactive("0")
    latency = reactive("--")
    evidence = reactive("--")

    def render(self) -> RenderableType:
        c = COLORS
        t = Text()
        t.append("\n")
        t.append("  Träffar:  ", style=c["sidebar_text_dim"])
        t.append(f"{self.hits}\n", style=c["sidebar_text"])
        t.append("  Token:    ", style=c["sidebar_text_dim"])
        t.append(f"{self.tokens}\n", style=c["sidebar_text"])
        t.append("  Svarstid: ", style=c["sidebar_text_dim"])
        t.append(f"{self.latency}\n", style=c["sidebar_text"])
        t.append("  Evidens:  ", style=c["sidebar_text_dim"])
        t.append(f"{self.evidence}\n", style=c["sidebar_text"])
        return t


class Sidebar(Widget):
    """Left sidebar container. Visibility toggled with ^T."""

    pass


class InputBar(Widget):
    """Enhanced input area with mode badge and status indicator."""

    status = reactive("READY")
    mode = reactive("auto")

    def render(self) -> RenderableType:
        c = COLORS
        st = self.status
        label = _STATE_LABELS.get(st, st)
        if st == "PROCESSING":
            badge_style = c["secondary"]
            badge = f"◐ {label}"
        elif st == "INPUT":
            badge_style = c["primary"]
            badge = f"● {label}"
        else:
            badge_style = c["text_dim"]
            badge = label

        t = Text()
        t.append(f"[{self.mode}]", style=c["text_dim"])
        t.append("    ", style="")
        t.append(badge, style=badge_style)
        return Align.right(t)


class FooterBar(Static):
    """Bottom bar with keybinding hints."""

    def render(self) -> RenderableType:
        c = COLORS
        t = Text()
        t.append(" ^C ", style=f"bold {c['text_dim']}")
        t.append("Avsluta   ", style=c["footer_text"])
        t.append("^L ", style=f"bold {c['text_dim']}")
        t.append("Rensa   ", style=c["footer_text"])
        t.append("^T ", style=f"bold {c['text_dim']}")
        t.append("Panel", style=c["footer_text"])

        version = Text()
        version.append("rag-cli v0.6.0", style=c["footer_text"])

        # Use Columns to space left/right
        return Columns([t, version], expand=True)


class MessageBlock(Widget):
    """Chat message block for the dark output zone."""

    content = reactive("")

    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content

    def render(self) -> RenderableType:
        time_str = datetime.now().strftime("%H:%M")
        c = COLORS
        avail = self.size.width - 4

        if self.role == "user":
            bubble_width = max(40, min(avail - 8, 70))
            header_text = Text()
            header_text.append("DU", style=c["user_bubble_border"])
            header_text.append(f" ── {time_str}", style=c["output_text_dim"])

            content_text = Text(self.content, style=c["output_text"])

            from rich.panel import Panel

            panel = Panel(
                content_text,
                title=header_text,
                title_align="right",
                border_style=c["user_bubble_border"],
                padding=(0, 1),
                style=f"on {c['user_bubble_bg']}",
                width=bubble_width,
            )
            return Align.right(panel, pad=False)

        elif self.role == "assistant":
            # Agent separator header line
            header = Text()
            header.append("── AGENT ", style=c["output_primary"])
            header.append("─" * max(1, avail - 22), style=c["output_border"])
            header.append(f" {time_str} ──", style=c["output_text_dim"])
            header.append("\n\n")

            # We render header + markdown content
            from rich.console import Group

            md = Markdown(
                self.content,
                code_theme="rag_neon",
            )
            return Group(header, md)

        elif self.role == "tool":
            header_text = Text()
            header_text.append("SYSTEM", style=c["output_tertiary"])

            return Syntax(
                self.content,
                "text",
                theme="rag_terminal",
                background_color=c["output_bg"],
                word_wrap=True,
            )

        return Text(self.content, style=c["output_text"])
