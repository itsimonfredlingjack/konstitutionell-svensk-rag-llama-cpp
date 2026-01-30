from typing import AsyncIterator, Awaitable, Callable, List

from vibe_cli.agent.context import ContextManager
from vibe_cli.config import AgentConfig
from vibe_cli.models.messages import Conversation, Message, Role, ToolCall, ToolResult
from vibe_cli.providers.base import LLMProvider, StreamChunk
from vibe_cli.tools.base import ToolRegistry


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        config: AgentConfig,
        on_confirmation: Callable[[str, dict], Awaitable[bool]] | None = None,
    ):
        self.provider = provider
        self.tools = tools
        self.config = config
        self.on_confirmation = on_confirmation
        self.conversation = Conversation(id="default")
        self.context_manager = ContextManager(provider)

    async def run(self, user_message: str) -> AsyncIterator[StreamChunk | ToolResult]:
        """Main agent loop with tool execution"""

        # Check if compression is needed before adding new message
        if self.context_manager.should_compress(self.conversation):
            self.conversation = await self.context_manager.compress(self.conversation)

        # Add user message
        self.conversation.add(Message(role=Role.USER, content=user_message))

        iteration = 0
        while iteration < self.config.max_iterations:
            iteration += 1

            # Get LLM response
            assistant_content = ""
            tool_calls: List[ToolCall] = []

            async for chunk in self.provider.complete(
                messages=self.conversation.messages,
                tools=self.tools.all_definitions(),
            ):
                if chunk.text:
                    assistant_content += chunk.text
                    yield chunk  # Stream text to UI

                if chunk.tool_calls:
                    tool_calls = chunk.tool_calls

                if chunk.done:
                    break

            # Add assistant message
            self.conversation.add(
                Message(
                    role=Role.ASSISTANT,
                    content=assistant_content,
                    tool_calls=tool_calls if tool_calls else None,
                )
            )

            # If no tool calls, we're done
            if not tool_calls:
                return

            # Execute tools
            results = []
            for tc in tool_calls:
                tool = self.tools.get(tc.name)

                # Confirmation for dangerous tools
                if tool and tool.definition.dangerous and self.config.require_confirmation:
                    if self.on_confirmation:
                        approved = await self.on_confirmation(tc.name, tc.arguments)
                        if not approved:
                            results.append(
                                ToolResult(
                                    tool_call_id=tc.id,
                                    content="User rejected tool execution",
                                    is_error=True,
                                )
                            )
                            continue

                # Execute
                result = await self.tools.execute(tc.name, tc.arguments)
                result.tool_call_id = tc.id
                result.tool_name = tc.name  # For UI command history
                results.append(result)
                yield result  # Stream tool results to UI

            # Add tool results to conversation
            self.conversation.add(
                Message(
                    role=Role.TOOL,
                    content="",
                    tool_results=results,
                )
            )

        # Max iterations reached
        yield StreamChunk(text="\n[Max iterations reached]", done=True)
