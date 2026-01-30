import asyncio
from pathlib import Path

from vibe_cli.models.tools import ToolParameter
from vibe_cli.tools.base import Tool, ToolDefinition, ToolResult


class GitStatusTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_status",
            description="Get current git status.",
            parameters=[],
            dangerous=False,
        )

    async def execute(self) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode() or "(no changes)"
            return ToolResult(tool_call_id="", content=output, is_error=proc.returncode != 0)
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)

class GitAddTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_add",
            description="Add files to staging area.",
            parameters=[
                ToolParameter(name="path", type="string", description="File path to add")
            ],
            dangerous=False,
        )

    async def execute(self, path: str) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "add", path,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return ToolResult(tool_call_id="", content=f"Added {path} to staging", is_error=False)
            return ToolResult(tool_call_id="", content=stderr.decode(), is_error=True)
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)

class GitCommitTool(Tool):
    def __init__(self, workspace: Path):
        self.workspace = workspace

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_commit",
            description="Commit staged changes.",
            parameters=[
                ToolParameter(name="message", type="string", description="Commit message")
            ],
            dangerous=True,
        )

    async def execute(self, message: str) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", message,
                cwd=self.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode() + stderr.decode()
            return ToolResult(tool_call_id="", content=output, is_error=proc.returncode != 0)
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error: {e}", is_error=True)
