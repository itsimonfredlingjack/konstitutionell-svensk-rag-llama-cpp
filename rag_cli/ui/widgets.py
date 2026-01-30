from __future__ import annotations

from datetime import datetime
from typing import Optional

import pygments.styles
from rich.align import Align
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Label, Static

from .theme import COLORS, HUD

# Register custom neon theme
pygments.styles.STYLE_MAP["rag_neon"] = "rag_cli.ui.theme:RagNeonStyle"
pygments.styles.STYLE_MAP["rag_terminal"] = "rag_cli.ui.theme:RagTerminalStyle"


class StatusBar(Static):
    """Minimal Input Status"""
    
    status = reactive("ready")
    
    def render(self) -> RenderableType:
        if self.status == "processing":
            return Text("PROCESSING...", style=COLORS["secondary"])
        elif self.status == "typing":
            return Text("INPUT", style=COLORS["primary"])
        return Text("READY", style=COLORS["text_dim"])


class AgentHeader(Widget):
    """Top-level HUD showing critical session data"""

    model = reactive("granite")
    tokens = reactive(0)
    branch = reactive("main")

    def render(self) -> RenderableType:
        # High-density block icon (Claude style)
        icon_col = f"[{COLORS['primary']}] ▟█▙[/]\n[{COLORS['primary']}] ▜█▛[/]"
        
        # Stacked data lines
        line1 = f" [bold {COLORS['text_bright']}]RAG CLI[/] [dim]v0.6.0[/]"
        line2 = f" [dim]{self.branch}[/] [{COLORS['text_dim']}]·[/] [{COLORS['secondary']}]{self.model}[/] [{COLORS['text_dim']}]·[/] [dim]{self.tokens} tks[/]"
        
        content = Text.from_markup(f"{icon_col.splitlines()[0]}{line1}\n{icon_col.splitlines()[1]}{line2}")
        
        return Align.left(content)


class MainframeBubble(Widget):
    """Professional Output Block"""

    content = reactive("")
    
    def __init__(self, role: str, content: str):
        super().__init__()
        self.role = role
        self.content = content

    def render(self) -> RenderableType:
        time_str = datetime.now().strftime("%H:%M")
        
        if self.role == "user":
            header = f"[{COLORS['primary']}]USER[/] [dim]{time_str}[/]"
            return Align.right(Panel(
                Text(self.content, style=COLORS["text"]),
                title=header,
                title_align="right",
                border_style=COLORS["surface_light"],
                box=HUD,
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
                width=60 
            ))
            
        elif self.role == "assistant":
            header = f"[{COLORS['secondary']}]AGENT[/] [dim]{time_str}[/]"
            return Align.left(Panel(
                Markdown(self.content),
                title=header,
                title_align="left",
                border_style=COLORS["surface_light"],
                box=HUD,
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
            ))
            
        elif self.role == "tool":
            header = f"[{COLORS['terminal_tertiary']}]SYSTEM[/]"
            return Panel(
                Syntax(
                    self.content,
                    "text",
                    theme="rag_terminal",
                    background_color=COLORS["terminal_bg"],
                    word_wrap=True,
                ),
                title=header,
                border_style=COLORS["terminal_border"],
                box=HUD,
                padding=(0, 1),
                style=f"on {COLORS['terminal_bg']}",
            )
            
        return Text(self.content)


class ConfirmationModal(ModalScreen[bool]):
    """Modal for confirming dangerous actions"""

    CSS = f"""
    ConfirmationModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
        import json
        args_json = json.dumps(self.arguments, indent=2)

        yield Container(
            Label(f"⚠ CONFIRM ACTION: {self.tool_name}", id="title"),
            Syntax(
                args_json,
                "json",
                theme="rag_neon",
                line_numbers=False,
                word_wrap=True,
                id="details",
            ),
            Button("CANCEL", variant="error", id="reject"),
            Button("EXECUTE", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)
