from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional

from pydantic import BaseModel

from vibe_cli.models.messages import Message, ToolCall
from vibe_cli.models.tools import ToolDefinition


class StreamChunk(BaseModel):
    text: str | None = None
    tool_calls: List[ToolCall] | None = None
    done: bool = False
    usage: dict | None = None

class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion with tool support"""
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Count tokens for context management"""
        ...
