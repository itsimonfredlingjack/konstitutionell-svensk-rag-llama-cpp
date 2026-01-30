# rag_cli/ui/app.py

import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.widgets import Input, Static

from rag_cli.config import Config
from rag_cli.providers.rag_backend import RAGBackendProvider

from .theme import CSS_VARS
from .widgets import AgentHeader, MainframeBubble, StatusBar


logger = logging.getLogger(__name__)

class ChatView(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield Static(id="top-spacer")

    def add_message(self, role: str, content: str) -> None:
        self.mount(MainframeBubble(role, content))
        self.scroll_end(animate=False)

    def stream_append(self, text: str) -> None:
        if self.children:
            last = self.children[-1]
            if isinstance(last, MainframeBubble) and last.role == "assistant":
                last.content += text
                last.refresh(layout=True)
                self.scroll_end(animate=False)


class RagApp(App):
    CSS = (
        CSS_VARS
        + """
    Screen { background: $bg; }
    
    /* === Professional Layout === */
    #layout-root {
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }
    
    /* Header Area */
    AgentHeader {
        dock: top;
        height: 4;
        margin: 0 0 1 0;
        padding: 0 2;
        border: round $surface_light;
        background: $surface;
    }
    
    /* Chat Area (Main) */
    #chat-area {
        height: 1fr;
        background: $bg;
        border: none;
    }
    
    #chat-view {
        height: 1fr;
        background: $terminal_bg;
        scrollbar-gutter: stable;
        padding: 1 2;
        margin: 0 0 1 0;
        border: round $terminal_border;
    }

    MainframeBubble {
        margin: 0 0 1 0;
    }

    #top-spacer {
        height: 1;
    }
    
    /* Input Box */
    #input-container {
        dock: bottom;
        height: auto;
        border: round $surface_light;
        background: $surface;
        padding: 0 2;
        margin: 0;
    }
    
    Input {
        border: round $surface_light;
        background: $surface_glow;
        color: $text;
        width: 100%;
        height: 3;
        padding: 0 1;
    }
    Input:focus { border: round $primary; }

    /* StatusBar */
    StatusBar {
        background: $surface;
        color: $text_dim;
        padding: 0 1;
    }
    """
    )

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workspace = Path.cwd()
        self.config = Config.load()
        self.rag_provider = RAGBackendProvider(base_url=self.config.rag_backend_url)
        self._last_sources: list[dict] = []

    def compose(self) -> ComposeResult:
        # Professional HUD Layout
        yield AgentHeader()

        with Container(id="layout-root"):
            with Vertical(id="chat-area"):
                yield ChatView(id="chat-view")
                with Container(id="input-container"):
                    yield Input(placeholder=">> COMMAND OR QUERY", id="input")
                    yield StatusBar(id="status-bar")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""

        status_bar = self.query_one(StatusBar)
        status_bar.status = "processing"

        chat = self.query_one("#chat-view", ChatView)
        chat.add_message("user", text)
        self.run_worker(self.process(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        status_bar = self.query_one(StatusBar)
        if event.value:
            status_bar.status = "typing"
        else:
            status_bar.status = "ready"

    async def process(self, text: str) -> None:
        chat = self.query_one("#chat-view", ChatView)
        status_bar = self.query_one(StatusBar)

        chat.add_message("assistant", "")
        assistant_text = ""

        try:
            async for chunk in self.rag_provider.query(text):
                if chunk.metadata and chunk.metadata.get("sources"):
                    self._last_sources = chunk.metadata["sources"]
                if chunk.text:
                    assistant_text += chunk.text
                    chat.stream_append(chunk.text)

            # Track conversation history (after query so current message is not duplicated)
            self.rag_provider.add_to_history("user", text)
            self.rag_provider.add_to_history("assistant", assistant_text)

            # Display sources if we got any
            if self._last_sources:
                sources_text = "\n\u2500\u2500 K\u00e4llor \u2500\u2500\n"
                for src in self._last_sources:
                    score = src.get("score", 0)
                    title = src.get("title", "Unknown")
                    sources_text += f"  [{score:.2f}] {title}\n"
                chat.add_message("tool", sources_text)
                self._last_sources = []

            status_bar.status = "ready"
        except Exception as e:
            chat.add_message("tool", f"CRITICAL_FAILURE: {e}")
            status_bar.status = "ready"

    def action_clear_screen(self) -> None:
        chat = self.query_one("#chat-view", ChatView)
        chat.remove_children()

if __name__ == "__main__":
    RagApp().run()
