# rag_cli/ui/app.py

import asyncio
import logging
from pathlib import Path

import aiofiles
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.widgets import Input, Static


from rag_cli.agent.loop import AgentLoop
from rag_cli.config import AgentConfig, Config
from rag_cli.providers.factory import build_provider
from rag_cli.tools.base import ToolRegistry
from rag_cli.tools.cloud import AWSResourceLister, K8sLogFetcher
from rag_cli.tools.filesystem import ReadFileTool, StrReplaceTool, WriteFileTool
from rag_cli.tools.git import GitAddTool, GitCommitTool, GitStatusTool
from rag_cli.tools.shell import ShellTool

from .theme import CSS_VARS
from .widgets import (
    AgentHeader,
    ConfirmationModal,
    MainframeBubble,
    StatusBar,
)


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
        padding: 0;
    }
    
    /* Header Area */
    AgentHeader {
        dock: top;
        height: 2;
        margin-bottom: 1;
        margin-left: 2;
        padding-top: 1;
    }
    
    /* Chat Area (Main) */
    #chat-area {
        height: 1fr;
        background: $bg;
        border: none;
    }
    
    #chat-view {
        height: 1fr;
        scrollbar-gutter: stable;
    }
    
    /* Input Box */
    #input-container {
        dock: bottom;
        height: auto;
        border-top: solid $surface_light;
        background: $surface;
        padding: 0 1;
        margin-top: 1;
    }
    
    Input {
        border: none;
        background: $surface;
        color: $text;
        width: 100%;
        height: 3;
    }
    Input:focus { border: none; }

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
        self.tools = ToolRegistry(load_plugins=False)
        self.tools.register(ReadFileTool(self.workspace))
        self.tools.register(WriteFileTool(self.workspace))
        self.tools.register(StrReplaceTool(self.workspace))
        self.tools.register(GitStatusTool(self.workspace))
        self.tools.register(GitAddTool(self.workspace))
        self.tools.register(GitCommitTool(self.workspace))
        self.tools.register(AWSResourceLister())
        self.tools.register(K8sLogFetcher())
        self.tools.register(ShellTool(self.workspace, allowed_commands=self.config.shell.allowed))

        provider_cfg = self.config.providers.get(self.config.default_provider)
        self.provider = build_provider(provider_cfg)
        self.agent = AgentLoop(self.provider, self.tools, AgentConfig(), on_confirmation=self._handle_confirmation)

    async def _handle_confirmation(self, tool_name: str, arguments: dict) -> bool:
        """Handle confirmation requests from the agent"""
        return await self.push_screen_wait(ConfirmationModal(tool_name, arguments))

    def on_mount(self) -> None:
        self.set_interval(10.0, self._poll_models)
        self.run_worker(self._load_plugins(), group="plugins")

    async def _load_plugins(self) -> None:
        await asyncio.to_thread(self.tools.register_plugins, self.workspace)

    async def _poll_models(self) -> None:
        try:
            models = await self.provider.get_available_models()
            if models:
                new_model = models[0]
                header = self.query_one(AgentHeader)
                if header.model != new_model:
                    header.model = new_model
        except Exception:
            pass

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

        try:
            async for chunk in self.agent.run(text):
                if hasattr(chunk, "text") and chunk.text:
                    chat.stream_append(chunk.text)
                elif hasattr(chunk, "tool_name") and chunk.tool_name:
                    chat.add_message("tool", chunk.content)
                    chat.add_message("assistant", "")

            status_bar.status = "ready"

        except Exception as e:
            chat.add_message("tool", f"CRITICAL_FAILURE: {e}")
            status_bar.status = "ready"

    def action_clear_screen(self) -> None:
        chat = self.query_one("#chat-view", ChatView)
        chat.remove_children()

if __name__ == "__main__":
    RagApp().run()