"""
Display module for RAG-Eval Terminal.
Handles all rendering using rich.
"""

from typing import Any
import time

from rich.align import Align
from rich.box import ROUNDED, HEAVY_EDGE
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.columns import Columns

try:
    from tools.rag_tester.core.api_client import Source
except ImportError:
    from core.api_client import Source  # noqa: TC002


class Dashboard:
    """Renders the main dashboard/welcome screen."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, stats: dict[str, Any]) -> None:
        """Render the dashboard with statistics."""
        self.console.clear()

        # Title - BIG ASCII ART
        logo_text = """
 [magenta]██████╗  █████╗  ██████╗[/]     [cyan]███████╗██╗   ██╗ █████╗ ██╗[/]
 [magenta]██╔══██╗██╔══██╗██╔════╝[/]     [cyan]██╔════╝██║   ██║██╔══██╗██║[/]
 [magenta]██████╔╝███████║██║  ███╗[/]    [cyan]█████╗  ██║   ██║███████║██║[/]
 [magenta]██╔══██╗██╔══██║██║   ██║[/]    [cyan]██╔══╝  ╚██╗ ██╔╝██╔══██║██║[/]
 [magenta]██║  ██║██║  ██║╚██████╔╝[/]    [cyan]███████╗ ╚████╔╝ ██║  ██║███████╗[/]
 [magenta]╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝[/]     [cyan]╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚══════╝[/]
        """
        title = Align.center(Text.from_markup(logo_text))
        subtitle = Text("Constitutional AI Quality Assurance", style="bold italic white")
        
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
            chars = [" ", " ", "▂", "▃", "▅", "▇"]
            sparkline_chars = []
            for r in trend_data:
                idx = min(max(r, 0), 5)
                color = "green" if r >= 4 else "yellow" if r >= 3 else "red"
                sparkline_chars.append(f"[{color}]{chars[idx]}[/]")
            sparkline = "".join(sparkline_chars)

        def make_stat_panel(label, value, color, icon, subtitle_text=None):
            content = [
                Align.center(Text(str(value), style=f"bold {color} sz 2"), vertical="middle")
            ]
            if subtitle_text:
                content.append(Align.center(subtitle_text))

            return Panel(
                Group(*content),
                title=f"[{color}]{icon} {label}[/{color}]",
                border_style=f"bold {color}",
                box=HEAVY_EDGE,
                padding=(1, 2),
            )

        grid.add_row(
            make_stat_panel("Tests Run", stats.get("total_ratings", 0), "bright_cyan", "🧪"),
            make_stat_panel("Avg Score", stats.get("avg_rating", "N/A"), "bright_green", "📊"),
            make_stat_panel(
                "Quality Trend", "", "bright_magenta", "📈", subtitle_text=Text.from_markup(sparkline or "No Data")
            ),
            make_stat_panel("Peak Rating", stats.get("max_rating", "N/A"), "gold1", "🏆"),
        )

        # Main Layout
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=8),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        header_panel = Panel(
            Group(title, Align.center(subtitle)),
            box=ROUNDED,
            style="magenta",
            border_style="magenta",
        )

        layout["header"].update(header_panel)
        layout["body"].update(Align.center(grid, vertical="middle"))
        
        # Footer
        footer_text = Text("Ready.", style="dim white")
        layout["footer"].update(Align.center(footer_text))

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
        # screen=False avoids alternate buffer conflicts with prompt_toolkit
        # transient=False keeps output visible after stream ends
        self.live = Live(self.layout, console=self.console, refresh_per_second=12, screen=False, transient=False)

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
                Text(self.question, style="bold white"),
                title="[b]Question",
                box=HEAVY_EDGE,
                border_style="blue",
            )
        )
        return layout

    def start(self):
        """Start the live display."""
        self.start_time = time.time()
        self.live.start()

    def stop(self):
        """Stop the live display."""
        self.live.stop()

    def persist(self):
        """Render the final static state to the console."""
        self.console.clear()
        self.console.print(self.layout)

    def update_token(self, token: str):
        """Add a token to the answer and update display."""
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
        self.end_time = time.time()
        self.is_done = True
        self._update_display()

    def _update_display(self):
        """Update all panels in the layout."""
        # Update Main Answer Panel
        if self.is_done and self.expected:
            # Side-by-side view
            left = Panel(
                Markdown(self.answer_text),
                title="[b]Actual Output[/b]",
                box=ROUNDED,
                border_style="bright_green",
            )
            right = Panel(
                Markdown(self.expected),
                title="[b]Gold Standard[/b]",
                box=ROUNDED,
                border_style="gold1",
            )

            content = Columns([left, right])
            self.layout["main"].update(content)
        else:
            # Normal view with glowing border effect
            # Flicker effect: use time to toggle colors
            colors = ["bright_green", "green", "bright_yellow", "yellow"]
            idx = int(time.time() * 2) % 4
            border_color = "bright_green" if self.is_done else "yellow"
            
            if not self.is_done:
                 border_color = colors[idx]

            md = Markdown(self.answer_text)
            
            # Mission Report Summary Card
            content_group = [md]
            if self.is_done:
                total_time = (self.end_time - self.start_time) if self.end_time and self.start_time else 0
                ttft = (self.first_token_time - self.start_time) if self.first_token_time and self.start_time else 0
                src_count = len(self.sources)
                
                # Create a mini-stats grid
                stats_grid = Table.grid(padding=(0, 2))
                stats_grid.add_column(justify="center")
                stats_grid.add_column(justify="center")
                stats_grid.add_column(justify="center")
                stats_grid.add_row(
                    f"[bold cyan]⏱️ {total_time:.2f}s[/]",
                    f"[bold magenta]⚡ {ttft*1000:.0f}ms TTFT[/]",
                    f"[bold green]📚 {src_count} Sources[/]"
                )
                
                summary_panel = Panel(
                    stats_grid,
                    title="[bold white]Mission Report[/]",
                    border_style="dim white",
                    box=ROUNDED,
                    padding=(0, 1)
                )
                content_group.append(Text("\n"))
                content_group.append(Align.center(summary_panel))

            self.layout["main"].update(
                Panel(
                    Group(*content_group),
                    title="[b]Generated Response[/b]",
                    box=ROUNDED,
                    border_style=border_color,
                )
            )

        # Update Sources Panel
        if self.sources:
            source_txt = Text()
            for i, s in enumerate(self.sources, 1):
                if isinstance(s, dict):
                    title = s.get("title", "Unknown")
                    score = s.get("score", 0.0)
                else:
                    title = getattr(s, "title", "Unknown")
                    score = getattr(s, "score", 0.0)
                
                # Style based on score
                s_style = "bold bright_green" if score > 0.8 else "cyan"
                source_txt.append(f"[{i}] ", style="dim")
                source_txt.append(f"{title} ", style=s_style)
                source_txt.append(f"[{score:.2f}]\n", style="dim white")

            self.layout["sources"].update(
                Panel(source_txt, title="[b]Sources Detected[/b]", box=ROUNDED, border_style="blue")
            )
        else:
            self.layout["sources"].update(
                Panel(
                    Text("Searching for relevant documents...", style="dim italic"),
                    title="[b]Sources[/b]",
                    box=ROUNDED,
                    border_style="dim white",
                )
            )

        # Update Status Pipeline
        # Visualizing the RAG stages: [1. Retrieve] -> [2. Think] -> [3. Generate] -> [4. Eval]
        pipeline = Text()
        
        # Stage 1: Retrieval
        if self.sources:
            pipeline.append(" ✔ Retrieved ", style="bold green")
        else:
            # Pulsing effect for active stage
            dots = "." * (int(time.time() * 3) % 4)
            pipeline.append(f" 🔍 Retrieving{dots} ", style="bold yellow")
            
        pipeline.append("➔", style="dim")

        # Stage 2: Generation
        if self.is_done:
            pipeline.append(" ✔ Generated ", style="bold green")
        elif self.sources and not self.is_done:
             pipeline.append(" ⚡ Generating... ", style="bold yellow blink")
        else:
             pipeline.append(" Generating ", style="dim white")

        pipeline.append("➔", style="dim")

        # Stage 3: Ready
        if self.is_done:
            pipeline.append(" 📝 Ready for Eval ", style="bold cyan")
        else:
            pipeline.append(" Eval ", style="dim white")

        # TTFT / Stats
        stats = []
        if self.first_token_time and self.start_time:
            ttft = (self.first_token_time - self.start_time) * 1000
            stats.append(f"TTFT: {ttft:.0f}ms")
        
        if self.is_done and self.end_time and self.start_time:
            total_time = (self.end_time - self.start_time)
            stats.append(f"Total: {total_time:.1f}s")

        stats_text = " | ".join(stats)
        
        self.layout["status"].update(
            Columns([
                Align.left(pipeline),
                Align.right(Text(stats_text, style="dim white"))
            ])
        )



class HistoryView:
    """Renders rating history."""

    def __init__(self, console: Console):
        self.console = console

    def render(self, history: list[dict]):
        """Render the history table."""
        table = Table(title="[bold magenta]Operational Logs[/]", box=HEAVY_EDGE, expand=True, border_style="magenta")
        table.add_column("Timestamp", style="dim cyan", no_wrap=True)
        table.add_column("Rating", justify="center")
        table.add_column("Comment", style="white")

        for entry in history:
            rating = entry.get("rating", 0)
            # Star bar
            stars = "[green]" + "★" * rating + "[/]" + "[dim]" + "☆" * (5 - rating) + "[/]"
            
            ts = entry.get("timestamp", "").split("T")[0]
            comment = entry.get("comment") or ""
            if len(comment) > 60:
                comment = comment[:57] + "..."

            table.add_row(ts, stars, comment)

        self.console.clear()
        self.console.print(table)
        self.console.print(Align.center(Text("\n[ Press Enter to return ]", style="bold dim white")))


class SourceInspector:
    """Renders a detailed view of sources with Tree visualization."""

    def __init__(self, console: Console):
        self.console = console

    async def show(self, sources: list[dict]):
        """Show sources in a paged manner."""

        if not sources:
            self.console.print("[yellow]No sources found.[/yellow]")
            import asyncio
            await asyncio.sleep(1)
            return

        current_idx = 0
        from prompt_toolkit import PromptSession
        session = PromptSession()

        while True:
            self.console.clear()
            source = sources[current_idx]

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

            # --- CIRCUIT BOARD HEADER (Visual Tracking) ---
            tree = Tree("🔍 [bold white]Retrieval Path[/]")
            vectordb = tree.add("📂 [bold cyan]Vector Store[/]")
            
            # Determine glow color
            if score > 0.8:
                glow_style = "bold bright_green"
                border_style = "green"
                doc_icon = "📄"
            elif score > 0.5:
                glow_style = "yellow"
                border_style = "yellow"
                doc_icon = "📄"
            else:
                glow_style = "dim red"
                border_style = "red"
                doc_icon = "⚠️"

            leaf = vectordb.add(f"{doc_icon} [bold]{title}[/]")
            
            # Visual Score Bar
            bar_len = 12
            filled = int(score * bar_len)
            bar_str = "█" * filled + "░" * (bar_len - filled)
            
            leaf.add(f"🎯 Relevance: [{glow_style}]{bar_str}[/] [white]({score:.1%})[/]")
            leaf.add(f"💾 File: [dim]{file_path}[/]")

            header_panel = Panel(
                tree,
                title="[bold magenta]Source Trace[/]",
                border_style="magenta",
                box=ROUNDED,
                padding=(1, 2)
            )

            # --- CONTENT PANEL ---
            content_display = Markdown(content) if content else Text("No content available", style="italic dim red")
            
            content_panel = Panel(
                content_display,
                title=f"[bold]Content Snippet[/]",
                subtitle=f"[dim]Source {current_idx + 1} of {len(sources)}[/dim]",
                border_style=border_style,
                box=HEAVY_EDGE,
                padding=(1, 2)
            )

            # Footer
            controls = Table.grid(expand=True)
            controls.add_column(justify="center")
            controls.add_row("[bold white]← Prev (P)[/]   [bold white]Next (N) →[/]   [bold red]Exit (Q)[/]")
            
            self.console.print(header_panel)
            self.console.print(content_panel)
            self.console.print(Panel(controls, style="dim", box=ROUNDED))

            # Input Loop
            choice = await session.prompt_async("Navigate > ")

            if choice.lower() == "q":
                break
            elif choice.lower() in ["n", ""]:
                current_idx = (current_idx + 1) % len(sources)
            elif choice.lower() in ["p", "b"]:
                current_idx = (current_idx - 1) % len(sources)