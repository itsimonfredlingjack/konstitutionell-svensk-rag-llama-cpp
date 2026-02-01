# rag_cli/ui/app.py

import logging
import time

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.timer import Timer
from textual.widgets import Input, Static

from rag_cli.config import Config
from rag_cli.providers.rag_backend import RAGBackendProvider

from .theme import COLORS, CSS_VARS, SIDEBAR_WIDTH
from .widgets import (
    SPINNER_FRAMES,
    FooterBar,
    HeaderBar,
    InputBar,
    MessageBlock,
    MetadataPanel,
    Sidebar,
    SourcesPanel,
    StatusPanel,
)

logger = logging.getLogger(__name__)


class ChatView(ScrollableContainer):
    """Dark-background scrollable chat area."""

    def compose(self) -> ComposeResult:
        yield Static(id="top-spacer")

    def add_message(self, role: str, content: str) -> None:
        self.mount(MessageBlock(role, content))
        self.scroll_end(animate=False)

    def stream_append(self, text: str) -> None:
        if self.children:
            last = self.children[-1]
            if isinstance(last, MessageBlock) and last.role == "assistant":
                last.content += text
                last.refresh(layout=True)
                self.scroll_end(animate=False)


class PlaceholderMessage(Static):
    """Centered placeholder when no messages exist."""

    def render(self):
        from rich.align import Align
        from rich.text import Text

        t = Text()
        t.append("Inga meddelanden \u00e4nnu.\n", style=COLORS["output_text_dim"])
        t.append("Skriv en fr\u00e5ga nedan.", style=COLORS["output_text_dim"])
        return Align.center(t)


class RagApp(App):
    CSS = (
        CSS_VARS
        + f"""
    Screen {{
        background: $bg;
    }}

    /* === HEADER === */
    HeaderBar {{
        dock: top;
        height: 2;
        background: $header_bg;
        color: $text;
        padding: 0 1;
        border-bottom: double $header_border;
    }}

    /* === MAIN CONTENT AREA === */
    #main-content {{
        height: 1fr;
        width: 1fr;
    }}

    /* === SIDEBAR === */
    Sidebar {{
        width: {SIDEBAR_WIDTH};
        background: $sidebar_bg;
        border-right: solid $sidebar_border;
    }}

    StatusPanel {{
        height: 8;
        margin-bottom: 1;
        padding: 0;
    }}

    SourcesPanel {{
        height: 1fr;
        min-height: 6;
        margin-bottom: 1;
        padding: 0;
    }}

    MetadataPanel {{
        height: 8;
        padding: 0;
    }}

    .sidebar-title {{
        dock: top;
        height: 1;
        background: $sidebar_title_bg;
        color: $sidebar_accent;
        padding: 0 1;
    }}

    /* === CHAT VIEW (dark zone) === */
    #chat-view {{
        background: $output_bg;
        color: {COLORS["output_text"]};
        scrollbar-gutter: stable;
        padding: 1 2;
        border-left: tall $output_border;
    }}

    #chat-view MessageBlock {{
        margin: 0 0 1 0;
        color: {COLORS["output_text"]};
    }}

    #top-spacer {{
        height: 0;
    }}

    PlaceholderMessage {{
        height: 1fr;
        content-align: center middle;
        color: {COLORS["output_text_dim"]};
    }}

    /* === INPUT BAR === */
    #input-bar {{
        dock: bottom;
        height: auto;
        max-height: 6;
        background: $input_bg;
        border-top: thick $input_border_dark;
        padding: 0 1;
    }}

    /* --- Inset frame: thick dark top+left, thick light bottom+right --- */
    #input-row {{
        height: 3;
        width: 1fr;
        background: $input_field_bg;
        border-top: thick $input_border_dark;
        border-left: thick $input_border_dark;
        border-bottom: thick $input_border_light;
        border-right: thick $input_border_light;
    }}

    /* Focus: form change (thick→double) + accent on border only */
    #input-row.focused {{
        border: double $input_focus_border;
    }}

    /* --- Prompt gutter --- */
    #input-prompt {{
        width: 5;
        height: 1;
        content-align: center middle;
        color: $text_dim;
        background: $input_gutter_bg;
        border-right: solid $input_gutter_sep;
    }}

    /* --- Text input (borderless — frame is on #input-row) --- */
    #query-input {{
        width: 1fr;
        border: none;
        background: transparent;
        color: $text;
        height: auto;
        padding: 0 1;
    }}
    #query-input:focus {{
        border: none;
    }}
    #query-input > .input--placeholder {{
        color: $placeholder_text;
    }}

    InputBar {{
        height: 1;
        width: 1fr;
        padding: 0 1;
    }}

    /* === FOOTER === */
    FooterBar {{
        dock: bottom;
        height: 1;
        background: $footer_bg;
        color: $footer_text;
        border-top: solid $footer_border;
        padding: 0 1;
    }}
    """
    )

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+t", "toggle_sidebar", "Sidebar"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.config = Config.load()
        self.rag_provider = RAGBackendProvider(base_url=self.config.rag_backend_url)
        self._last_sources: list[dict] = []
        self._sidebar_visible: bool = self.config.ui.sidebar_visible
        self._token_count: int = 0
        self._spinner_index: int = 0
        self._spinner_timer: Timer | None = None
        self._processing_start: float = 0.0

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header")
        with Horizontal(id="main-content"):
            with Sidebar(id="sidebar"):
                yield Static("▌ STATUS", classes="sidebar-title")
                yield StatusPanel(id="status-panel")
                yield Static("▌ KÄLLOR", classes="sidebar-title")
                yield SourcesPanel(id="sources-panel")
                yield Static("▌ DATA", classes="sidebar-title")
                yield MetadataPanel(id="metadata-panel")
            yield ChatView(id="chat-view")
        with Vertical(id="input-bar"):
            with Horizontal(id="input-row"):
                yield Static(">>", id="input-prompt")
                yield Input(placeholder="Ställ en fråga...", id="query-input")
            yield InputBar(id="input-badge")
        yield FooterBar(id="footer")

    def on_mount(self) -> None:
        """Set initial sidebar visibility and show placeholder."""
        if not self._sidebar_visible:
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.display = False
        # Show placeholder in empty chat
        chat = self.query_one("#chat-view", ChatView)
        chat.mount(PlaceholderMessage(id="placeholder"))
        # Parse backend URL for header display
        header = self.query_one("#header", HeaderBar)
        url = self.config.rag_backend_url
        header.backend_url = url.replace("http://", "").replace("https://", "")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        self._set_state("PROCESSING")

        # Update last_query in sidebar
        status_panel = self.query_one("#status-panel", StatusPanel)
        status_panel.last_query = text

        chat = self.query_one("#chat-view", ChatView)
        # Remove placeholder if present
        try:
            placeholder = chat.query_one("#placeholder", PlaceholderMessage)
            placeholder.remove()
        except Exception:
            pass

        chat.add_message("user", text)
        self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.value:
            self._set_state("INPUT")
        else:
            self._set_state("IDLE")

    def on_descendant_focus(self, event) -> None:
        """Add focused class to input row frame when query input gains focus."""
        if hasattr(event, "widget") and getattr(event.widget, "id", None) == "query-input":
            self.query_one("#input-row").add_class("focused")

    def on_descendant_blur(self, event) -> None:
        """Remove focused class from input row frame when query input loses focus."""
        if hasattr(event, "widget") and getattr(event.widget, "id", None) == "query-input":
            self.query_one("#input-row").remove_class("focused")

    def _set_state(self, state: str) -> None:
        """Propagate state to header, sidebar status panel, and input bar."""
        header = self.query_one("#header", HeaderBar)
        status_panel = self.query_one("#status-panel", StatusPanel)
        input_bar = self.query_one("#input-badge", InputBar)

        if state == "PROCESSING":
            header.status = "PROCESSING"
            status_panel.state = "PROCESSING"
            input_bar.status = "PROCESSING"
            self._processing_start = time.monotonic()
            self._start_spinner()
        elif state == "INPUT":
            header.status = "INPUT"
            status_panel.state = "INPUT"
            input_bar.status = "INPUT"
            self._stop_spinner()
        elif state == "ERROR":
            header.status = "ERROR"
            status_panel.state = "ERROR"
            input_bar.status = "ERROR"
            self._stop_spinner()
        else:
            header.status = "READY"
            status_panel.state = "IDLE"
            input_bar.status = "READY"
            self._stop_spinner()

    def _start_spinner(self) -> None:
        """Start the processing spinner animation."""
        if self._spinner_timer is None:
            self._spinner_index = 0
            self._spinner_timer = self.set_interval(0.15, self._tick_spinner)

    def _stop_spinner(self) -> None:
        """Stop the processing spinner animation."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _tick_spinner(self) -> None:
        """Advance spinner frame and update header."""
        self._spinner_index = (self._spinner_index + 1) % len(SPINNER_FRAMES)
        header = self.query_one("#header", HeaderBar)
        header.status = "PROCESSING"
        header.refresh()

    async def process(self, text: str) -> None:
        chat = self.query_one("#chat-view", ChatView)
        metadata_panel = self.query_one("#metadata-panel", MetadataPanel)
        sources_panel = self.query_one("#sources-panel", SourcesPanel)

        chat.add_message("assistant", "")
        assistant_text = ""
        self._token_count = 0

        # Reset metadata for new query
        metadata_panel.hits = "--"
        metadata_panel.tokens = "0"
        metadata_panel.latency = "--"
        metadata_panel.evidence = "--"
        sources_panel.sources = []

        try:
            async for chunk in self.rag_provider.query(text):
                if chunk.metadata:
                    if chunk.metadata.get("sources"):
                        self._last_sources = chunk.metadata["sources"]
                    # Extract metadata fields
                    if chunk.metadata.get("total_results"):
                        metadata_panel.hits = str(chunk.metadata["total_results"])
                    if chunk.metadata.get("evidence_level"):
                        metadata_panel.evidence = chunk.metadata["evidence_level"]
                if chunk.text:
                    assistant_text += chunk.text
                    self._token_count += 1
                    metadata_panel.tokens = str(self._token_count)
                    chat.stream_append(chunk.text)

            # Final metadata
            elapsed = time.monotonic() - self._processing_start
            metadata_panel.latency = f"{elapsed:.1f}s"

            self.rag_provider.add_to_history("user", text)
            self.rag_provider.add_to_history("assistant", assistant_text)

            if self._last_sources:
                # Update sidebar sources
                sources_panel.sources = list(self._last_sources)
                metadata_panel.hits = str(len(self._last_sources))

                # Show sources inline in chat
                sources_text = "\n\u2500\u2500 K\u00e4llor \u2500\u2500\n"
                for src in self._last_sources:
                    score = src.get("score", 0)
                    title = src.get("title", "Unknown")
                    sources_text += f"  [{score:.2f}] {title}\n"
                chat.add_message("tool", sources_text)
                self._last_sources = []

            self._set_state("IDLE")

        except httpx.ConnectError:
            chat.add_message(
                "tool",
                "CONNECTION ERROR: Could not reach backend at "
                f"{self.rag_provider.base_url}\n"
                "Make sure the Constitutional AI backend is running.",
            )
            header = self.query_one("#header", HeaderBar)
            header.backend_online = False
            status_panel = self.query_one("#status-panel", StatusPanel)
            status_panel.backend_online = False
            self._set_state("ERROR")
        except httpx.TimeoutException:
            chat.add_message(
                "tool",
                "TIMEOUT: Backend did not respond within "
                f"{self.rag_provider.timeout}s.\n"
                "The query may be too complex or the server is overloaded.",
            )
            self._set_state("ERROR")
        except Exception as e:
            chat.add_message("tool", f"ERROR: {type(e).__name__}: {e}")
            self._set_state("ERROR")

    def action_clear_screen(self) -> None:
        chat = self.query_one("#chat-view", ChatView)
        chat.remove_children()
        chat.mount(PlaceholderMessage(id="placeholder"))

        # Reset sidebar
        metadata_panel = self.query_one("#metadata-panel", MetadataPanel)
        sources_panel = self.query_one("#sources-panel", SourcesPanel)
        metadata_panel.hits = "--"
        metadata_panel.tokens = "0"
        metadata_panel.latency = "--"
        metadata_panel.evidence = "--"
        sources_panel.sources = []

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.display = not sidebar.display
        self._sidebar_visible = sidebar.display


if __name__ == "__main__":
    RagApp().run()
