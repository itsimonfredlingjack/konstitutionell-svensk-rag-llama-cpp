"""
NERDY AI - SAFE UI
Static rendering functions that don't break the terminal.
"""

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from .assets import AVATAR_STATIC, BANNER, Colors

console = Console()


def clear_screen():
    console.clear()


def print_startup():
    """Prints the startup banner and avatar."""
    # Combine Banner and Avatar side-by-side or stacked?
    # Stacked is safer for narrow terminals.

    console.print(
        Panel(
            Align.center(Text(BANNER, style=Colors.HEADER_TEXT)),
            style=Colors.BORDER,
            box=box.ROUNDED,
            padding=(1, 2),
            subtitle="[dim]SAFE MODE v1.0[/]",
        )
    )

    console.print(Align.center(Text(AVATAR_STATIC, style=Colors.ACCENT)))
    console.print(Rule(style=Colors.DIM))


def print_user_message(text: str):
    """Prints the user's message with styling."""
    console.print()
    console.print(f"[{Colors.USER_PREFIX}]> USER:[/] {text}")


def print_ai_header():
    """Prints the header before AI streaming starts."""
    console.print(f"[{Colors.AI_PREFIX}]◈ NERDY:[/] ", end="")


def print_stream_token(token: str):
    """Safe print for streaming."""
    print(token, end="", flush=True)


def print_end_turn():
    """Prints a separator after the turn."""
    print()  # Newline after stream
    console.print(Rule(style=Colors.DIM))


def print_error(msg: str):
    console.print(f"[{Colors.ERROR}]ERROR:[/] {msg}")


def print_system(msg: str):
    console.print(f"[{Colors.DIM}]▸ {msg}[/]")


def show_status(message: str, status_type: str = "info"):
    """Show a status message with color based on type."""
    color_map = {
        "success": "bold green",
        "error": "bold red",
        "warning": "bold yellow",
        "info": "bold cyan",
    }
    color = color_map.get(status_type, "white")
    console.print(f"[{color}]{message}[/]")
