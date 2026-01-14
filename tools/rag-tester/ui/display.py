"""
Display module for RAG-Eval Terminal.
Handles all rendering using rich.
"""

from typing import TYPE_CHECKING, Any

from rich.align import Align
from rich.box import HEAVY, ROUNDED
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    try:
        from tools.rag_tester.core.api_client import Source
    except ImportError:
        from core.api_client import Source


class Dashboard:
    """Renders the main dashboard/welcome screen."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, stats: dict[str, Any]) -> None:
        """Render the dashboard with statistics."""
        self.console.clear()

        # Title
        title = Text("RAG-Eval Terminal", style="bold magenta", justify="center")
        subtitle = Text("Constitutional AI Quality Assurance", style="dim white", justify="center")

        # Stats Grid
        grid = Table.grid(expand=True, padding=(1, 2))
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)
        grid.add_column(justify="center", ratio=1)

        # Sparkline logic
        trend_data = stats.get("trend_data", [])
        sparkline = ""
        if trend_data:
            # Simple mapping 1-5 to valid chars
            #  ▂▃▅▇ -> relative height? Or just map 1= , 2=▂, 3=▃, 4=▅, 5=▇
            # Let's map 1-5 directly for simplicity, assuming data is ratings.
            chars = [" ", " ", "▂", "▃", "▅", "▇"]  # 0-5 index (0 is unused usually)
            sparkline = "".join([chars[r] if 0 <= r <= 5 else "?" for r in trend_data])
            # Add some color
            sparkline = f"[{'green' if trend_data[-1] >= 4 else 'yellow'}]{sparkline}[/]"

        def make_stat_panel(label, value, color, subtitle=None):
            content = [
                Align.center(Text(str(value), style=f"bold {color} sz 2"), vertical="middle")
            ]
            if subtitle:
                content.append(Align.center(subtitle))

            from rich.console import Group

            return Panel(
                Group(*content),
                title=f"[{color}]{label}[/{color}]",
                border_style=color,
                box=ROUNDED,
                padding=(1, 2),
            )

        grid.add_row(
            make_stat_panel("Total Tests", stats.get("total_ratings", 0), "cyan"),
            make_stat_panel("Avg Rating", stats.get("avg_rating", "N/A"), "green"),
            make_stat_panel(
                "Quality Trend", "", "magenta", subtitle=Text.from_markup(sparkline or "No Data")
            ),
            make_stat_panel("Max Rating", stats.get("max_rating", "N/A"), "gold1"),
        )

        # Main Layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        layout["header"].update(Panel(Align.center(title), box=HEAVY, style="magenta"))
        layout["body"].update(Align.center(grid, vertical="middle"))
        layout["footer"].update(Align.center(subtitle))

        self.console.print(layout)


class StreamRenderer:
    """StreamRenderer class with TTFT and Diff support"""

    def __init__(self, console: Console, question: str, expected: str | None = None):
        self.console = console
        self.question = question
        self.expected = expected
        self.answer_text = ""
        self.sources: list[Source] = []
        self.is_done = False

        # Timing
        self.start_time = None
        self.first_token_time = None
        self.end_time = None

        self.layout = self._make_layout()
        self.live = Live(self.layout, console=self.console, refresh_per_second=10, screen=True)

    def _make_layout(self) -> Layout:
        """Create the layout structure."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=3),
            Layout(name="sources", size=6),
            Layout(name="status", size=1),
        )

        # Set static header
        layout["header"].update(
            Panel(
                Text(self.question, style="bold cyan"),
                title="[b]Question",
                box=ROUNDED,
                border_style="cyan",
            )
        )
        return layout

    def start(self):
        """Start the live display."""
        import time

        self.start_time = time.time()
        self.live.start()

    def stop(self):
        """Stop the live display."""
        self.live.stop()

    def update_token(self, token: str):
        """Add a token to the answer and update display."""
        import time

        if self.first_token_time is None:
            self.first_token_time = time.time()

        self.answer_text += token
        self._update_display()

    def set_sources(self, sources: list[dict]):
        """Set the sources list."""
        self.sources = sources
        self._update_display()

    def get_sources(self) -> list[dict]:
        """Return the captured sources."""
        return self.sources

    def done(self):
        """Mark as done."""
        import time

        self.end_time = time.time()
        self.is_done = True
        self._update_display()

    def _update_display(self):
        """Update all panels in the layout."""
        # Update Main Answer Panel
        # If we have an expected answer and we are done, show diff
        if self.is_done and self.expected:
            # Side-by-side view
            from rich.columns import Columns

            left = Panel(
                Markdown(self.answer_text),
                title="[b]Actual Answer",
                box=ROUNDED,
                border_style="green",
            )
            right = Panel(
                Markdown(self.expected),
                title="[b]Expected (Gold)",
                box=ROUNDED,
                border_style="gold1",
            )

            # Simple columns
            content = Columns([left, right])
            self.layout["main"].update(content)
        else:
            # Normal view
            md = Markdown(self.answer_text)
            self.layout["main"].update(
                Panel(
                    md,
                    title="[b]Answer",
                    box=ROUNDED,
                    border_style="green" if self.is_done else "yellow",
                )
            )

        # Update Sources Panel
        if self.sources:
            source_txt = Text()
            for i, s in enumerate(self.sources, 1):
                # Handle both dict and object
                if isinstance(s, dict):
                    title = s.get("title", "Unknown")
                    score = s.get("score", 0.0)
                else:
                    title = getattr(s, "title", "Unknown")
                    score = getattr(s, "score", 0.0)

                source_txt.append(f"[{i}] {title} ", style="bold white")
                source_txt.append(f"(Score: {score:.2f})\n", style="dim white")

            self.layout["sources"].update(
                Panel(source_txt, title="[b]Sources", box=ROUNDED, border_style="blue")
            )
        else:
            self.layout["sources"].update(
                Panel(
                    Text("Waiting for sources...", style="dim italic"),
                    title="[b]Sources",
                    box=ROUNDED,
                    border_style="dim white",
                )
            )

        # Update Status
        if self.is_done:
            # Calc stats
            total_time = (
                (self.end_time - self.start_time) if (self.end_time and self.start_time) else 0.0
            )
            ttft = (
                (self.first_token_time - self.start_time)
                if (self.first_token_time and self.start_time)
                else 0.0
            )

            status_text = f"✔ Done in {total_time:.2f}s (TTFT: {ttft:.2f}s)"
            status = Text(status_text, style="bold green")
        else:
            # Show live timer?
            import time

            current = time.time()
            elapsed = current - self.start_time if self.start_time else 0.0
            status = Spinner("dots", text=f"Generating... ({elapsed:.1f}s)", style="yellow")

        self.layout["status"].update(Align.right(status))


class HistoryView:
    """Renders rating history."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, history: list[dict]):
        """Render the history table."""
        table = Table(title="Rating History", box=ROUNDED, expand=True)
        table.add_column("Date", style="dim", no_wrap=True)
        table.add_column("Rating", justify="center")
        table.add_column("Comment")

        for entry in history:
            rating = entry.get("rating", 0)
            stars = "⭐" * rating
            # Parse timestamp if strictly ISO, for now just show string
            ts = entry.get("timestamp", "").split("T")[0]

            table.add_row(ts, stars, entry.get("comment") or "")

        self.console.clear()
        self.console.print(table)
        self.console.print(Align.center(Text("\nPress Enter to return", style="dim")))


class SourceInspector:
    """Renders a detailed view of sources."""

    def __init__(self, console: Console):
        self.console = console

    async def show(self, sources: list[dict]):
        """Show sources in a paged manner."""

        if not sources:
            self.console.print("[yellow]No sources to inspect.[/yellow]")
            import asyncio

            await asyncio.sleep(1)
            return

        current_idx = 0
        while True:
            self.console.clear()
            source = sources[current_idx]

            # Prepare Content
            # Handle both dict and object
            if isinstance(source, dict):
                title = source.get("title", "Unknown")
                score = source.get("score", 0.0)
                file_path = source.get("source", "N/A")
                content = source.get("snippet", "")
            else:
                title = getattr(source, "title", "Unknown")
                score = getattr(source, "score", 0.0)
                file_path = getattr(source, "source", "N/A")
                content = getattr(source, "snippet", "")

            # Header
            header = Text(
                f"Source Inspector ({current_idx + 1}/{len(sources)})",
                style="bold magenta",
                justify="center",
            )

            # Metadata Panel
            meta_grid = Table.grid(padding=(0, 2))
            meta_grid.add_column(style="bold cyan")
            meta_grid.add_column()
            meta_grid.add_row("Title:", title)
            meta_grid.add_row("Score:", f"{score:.4f}")
            meta_grid.add_row("File:", file_path)

            meta_panel = Panel(meta_grid, title="Metadata", border_style="cyan", box=ROUNDED)

            # Content Panel
            # content might be markdown or just text
            content_panel = Panel(
                Markdown(content)
                if content
                else Text("No content snippet available", style="italic dim"),
                title="Content Snippet",
                border_style="green",
                box=ROUNDED,
                padding=(1, 1),
            )

            # Footer instructions
            footer = Text("\n[n] Next   [p] Prev   [q] Exit", style="dim white", justify="center")

            self.console.print(Align.center(header))
            self.console.print(meta_panel)
            self.console.print(content_panel)
            self.console.print(footer)

            # Simple non-blocking input wait?
            # We are in async context, so we can use prompt_toolkit's prompt in a thread or patching.
            # But earlier we used `await ...run_async()`.
            # `prompt` is synchronous. `session.prompt_async()` is async.
            from prompt_toolkit import PromptSession

            session = PromptSession()
            choice = await session.prompt_async("Navigation > ")

            if choice.lower() == "q":
                break
            elif choice.lower() in [
                "n",
                "",
            ]:  # right/next logic if using typical vim keys or just enter
                current_idx = (current_idx + 1) % len(sources)
            elif choice.lower() in ["p", "b"]:  # left/prev
                current_idx = (current_idx - 1) % len(sources)
