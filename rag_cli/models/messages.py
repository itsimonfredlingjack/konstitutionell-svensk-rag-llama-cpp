from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class ToolResult(BaseModel):
    tool_call_id: str
    content: str
    is_error: bool = False
    tool_name: str = ""  # For UI display


class Message(BaseModel):
    role: Role
    content: str | list[dict]
    tool_calls: list[ToolCall] | None = None
    tool_results: list[ToolResult] | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    tokens: int | None = None


class Conversation(BaseModel):
    id: str
    messages: List[Message] = Field(default_factory=list)
    total_tokens: int = 0
    created_at: datetime = Field(default_factory=datetime.now)

    def add(self, msg: Message) -> None:
        self.messages.append(msg)
        if msg.tokens:
            self.total_tokens += msg.tokens
