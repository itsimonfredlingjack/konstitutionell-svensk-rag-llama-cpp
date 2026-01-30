from unittest.mock import AsyncMock

import pytest

from vibe_cli.agent.loop import AgentLoop
from vibe_cli.config import AgentConfig
from vibe_cli.models.messages import ToolCall, ToolResult
from vibe_cli.models.tools import ToolDefinition
from vibe_cli.providers.base import LLMProvider, StreamChunk
from vibe_cli.tools.base import Tool, ToolRegistry


class MockProvider(LLMProvider):
    def __init__(self):
        super().__init__()
        self.model = "mock-model"

    async def complete(self, messages, tools=None):
        # Simulate a tool call in the first chunk
        yield StreamChunk(
            tool_calls=[ToolCall(id="1", name="dangerous_tool", arguments={"force": True})],
            done=False
        )
        yield StreamChunk(done=True)

    async def get_available_models(self):
        return ["mock-model"]

    async def count_tokens(self, text: str) -> int:
        return len(text.split())

class DangerousTool(Tool):
    def __init__(self):
        self._def = ToolDefinition(
            name="dangerous_tool",
            description="Dangerous",
            dangerous=True,
            parameters=[]
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._def

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool_call_id="mock", content="Executed")

@pytest.mark.asyncio
async def test_agent_loop_confirmation_approved():
    tools = ToolRegistry()
    tools.register(DangerousTool())

    config = AgentConfig(require_confirmation=True, max_iterations=1)
    provider = MockProvider()

    # Callback
    on_confirmation = AsyncMock(return_value=True)

    agent = AgentLoop(provider, tools, config, on_confirmation=on_confirmation)

    # Run
    results = []
    async for chunk in agent.run("Do something dangerous"):
        results.append(chunk)

    # Verify confirmation was called
    on_confirmation.assert_awaited_once_with("dangerous_tool", {"force": True})

    # Verify tool was executed
    tool_results = [r for r in results if hasattr(r, 'tool_name') and r.tool_name == "dangerous_tool"]
    assert len(tool_results) == 1
    assert tool_results[0].content == "Executed"


@pytest.mark.asyncio
async def test_agent_loop_confirmation_rejected():
    tools = ToolRegistry()
    tools.register(DangerousTool())

    config = AgentConfig(require_confirmation=True, max_iterations=1)
    provider = MockProvider()

    # Callback
    on_confirmation = AsyncMock(return_value=False)

    agent = AgentLoop(provider, tools, config, on_confirmation=on_confirmation)

    # Run
    results = []
    async for chunk in agent.run("Do something dangerous"):
        results.append(chunk)

    # Verify confirmation was called
    on_confirmation.assert_awaited_once_with("dangerous_tool", {"force": True})

    # Verify tool was NOT executed (yielded)
    tool_results = [r for r in results if hasattr(r, 'tool_name') and r.tool_name == "dangerous_tool"]
    assert len(tool_results) == 0
