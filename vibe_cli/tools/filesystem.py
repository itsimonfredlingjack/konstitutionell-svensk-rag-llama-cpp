from pathlib import Path

import aiofiles

from vibe_cli.models.tools import ToolParameter
from vibe_cli.tools.base import Tool, ToolDefinition, ToolResult


class ReadFileTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read contents of a file. Returns file content with line numbers.",
            parameters=[
                ToolParameter(name="path", type="string", description="Relative path from workspace root"),
                ToolParameter(name="start_line", type="integer", description="Start line (1-indexed)", required=False),
                ToolParameter(name="end_line", type="integer", description="End line (1-indexed, -1 for end)", required=False),
            ],
            dangerous=False,
        )

    async def execute(self, path: str, start_line: int = 1, end_line: int = -1) -> ToolResult:
        try:
            full_path = (self.workspace / path).resolve()

            # Security: ensure path is within workspace
            if not str(full_path).startswith(str(self.workspace.resolve())):
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: Path escapes workspace: {path}",
                    is_error=True,
                )

            if not full_path.exists():
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: File not found: {path}",
                    is_error=True,
                )

            async with aiofiles.open(full_path, "r") as f:
                lines = await f.readlines()

            # Apply line range
            if end_line == -1:
                end_line = len(lines)

            selected = lines[start_line - 1 : end_line]

            # Format with line numbers
            numbered = [
                f"{i + start_line:4d} │ {line.rstrip()}"
                for i, line in enumerate(selected)
            ]

            return ToolResult(
                tool_call_id="",
                content=f"File: {path} (lines {start_line}-{end_line} of {len(lines)})\n" + "\n".join(numbered),
                is_error=False,
            )

        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)


class WriteFileTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Write content to a file. Creates parent directories if needed.",
            parameters=[
                ToolParameter(name="path", type="string", description="Relative path from workspace root"),
                ToolParameter(name="content", type="string", description="Full file content to write"),
            ],
            dangerous=True,
        )

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            full_path = (self.workspace / path).resolve()

            if not str(full_path).startswith(str(self.workspace.resolve())):
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: Path escapes workspace: {path}",
                    is_error=True,
                )

            full_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(full_path, "w") as f:
                await f.write(content)

            lines = content.count("\n") + 1
            return ToolResult(
                tool_call_id="",
                content=f"Wrote {lines} lines to {path}",
                is_error=False,
            )

        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)


class StrReplaceTool(Tool):
    """Partial file edit with fuzzy matching for error recovery"""

    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="str_replace",
            description="Replace a unique string in a file. The old_str must appear exactly once.",
            parameters=[
                ToolParameter(name="path", type="string", description="Relative path from workspace root"),
                ToolParameter(name="old_str", type="string", description="Exact string to find (must be unique)"),
                ToolParameter(name="new_str", type="string", description="Replacement string"),
            ],
            dangerous=True,
        )

    async def execute(self, path: str, old_str: str, new_str: str) -> ToolResult:
        try:
            full_path = (self.workspace / path).resolve()

            if not str(full_path).startswith(str(self.workspace.resolve())):
                return ToolResult(tool_call_id="", content="Error: Path escapes workspace", is_error=True)

            if not full_path.exists():
                return ToolResult(tool_call_id="", content=f"Error: File not found: {path}", is_error=True)

            async with aiofiles.open(full_path, "r") as f:
                content = await f.read()

            count = content.count(old_str)

            if count == 0:
                # Fuzzy match attempt for helpful error message
                similar = self._find_similar(content, old_str)
                if similar:
                    return ToolResult(
                        tool_call_id="",
                        content=f"Error: String not found. Did you mean:\n```\n{similar}\n```",
                        is_error=True,
                    )
                return ToolResult(tool_call_id="", content="Error: String not found in file", is_error=True)

            if count > 1:
                return ToolResult(
                    tool_call_id="",
                    content=f"Error: String appears {count} times. Must be unique. Add more context to old_str.",
                    is_error=True,
                )

            new_content = content.replace(old_str, new_str, 1)

            async with aiofiles.open(full_path, "w") as f:
                await f.write(new_content)

            return ToolResult(tool_call_id="", content=f"Successfully replaced string in {path}", is_error=False)

        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)

    def _find_similar(self, content: str, target: str, threshold: float = 0.6) -> str | None:
        """Find similar strings using difflib for error recovery"""
        from difflib import SequenceMatcher

        lines = content.splitlines()
        target_lines = target.splitlines()

        best_match = None
        best_ratio = threshold

        # Slide window of same size as target
        window_size = len(target_lines)
        if window_size == 0:
            return None

        for i in range(len(lines) - window_size + 1):
            candidate = "\n".join(lines[i : i + window_size])
            ratio = SequenceMatcher(None, target, candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = candidate

        return best_match
