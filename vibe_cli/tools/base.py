import importlib.util
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from types import ModuleType

from vibe_cli.models.tools import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)

# Security: Disable workspace plugin loading by default
# Set VIBE_ALLOW_WORKSPACE_PLUGINS=1 to enable loading plugins from .vibe/tools/
ALLOW_WORKSPACE_PLUGINS = os.environ.get("VIBE_ALLOW_WORKSPACE_PLUGINS", "0") == "1"


class Tool(ABC):
    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return tool schema for LLM"""
        ...

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool"""
        ...

class ToolRegistry:
    def __init__(self, plugin_dir: Path | None = None, load_plugins: bool = True):
        self._tools: dict[str, Tool] = {}
        if load_plugins:
            self.load_plugins(plugin_dir)

    def register(self, tool: Tool) -> None:
        self._tools[tool.definition.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all_definitions(self) -> list[ToolDefinition]:
        return [t.definition for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                tool_call_id="",
                content=f"Unknown tool: {name}",
                is_error=True,
            )
        return await tool.execute(**arguments)

    def load_plugins(self, plugin_dir: Path | None = None) -> None:
        base_dir = plugin_dir or self._default_plugin_dir()
        if not base_dir.exists():
            return

        for path in sorted(base_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module = self._load_module(path)
            if not module:
                continue
            for tool in self._extract_tools(module):
                self.register(tool)

    def register_plugins(self, workspace: Path) -> None:
        """Load plugins from workspace .vibe/tools/ directory.

        SECURITY: Disabled by default. Set VIBE_ALLOW_WORKSPACE_PLUGINS=1 to enable.
        Loading arbitrary Python code from workspaces is a security risk.
        """
        if not ALLOW_WORKSPACE_PLUGINS:
            plugin_dir = workspace / ".vibe" / "tools"
            if plugin_dir.exists() and any(plugin_dir.glob("*.py")):
                logger.warning(
                    "Workspace plugins found in %s but loading is disabled. "
                    "Set VIBE_ALLOW_WORKSPACE_PLUGINS=1 to enable (security risk).",
                    plugin_dir,
                )
            return
        self.load_plugins(workspace / ".vibe" / "tools")

    def _default_plugin_dir(self) -> Path:
        return Path.cwd() / ".vibe" / "tools"

    def _load_module(self, path: Path) -> ModuleType | None:
        module_name = f"vibe_cli_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("Failed to load plugin module: %s", path)
            return None
        return module

    def _extract_tools(self, module: ModuleType) -> list[Tool]:
        if hasattr(module, "get_tools"):
            tools = module.get_tools()
            return self._normalize_tools(tools)
        if hasattr(module, "load_tools"):
            tools = module.load_tools()
            return self._normalize_tools(tools)
        if hasattr(module, "TOOLS"):
            return self._normalize_tools(module.TOOLS)
        return []

    def _normalize_tools(self, tools: object) -> list[Tool]:
        if isinstance(tools, Tool):
            return [tools]
        if isinstance(tools, list):
            return [tool for tool in tools if isinstance(tool, Tool)]
        return []
