"""OpenCode CLI provider - routes through opencode for z.ai/GLM access."""

import asyncio
from typing import AsyncIterator

from rag_cli.models.messages import Message, Role
from rag_cli.models.tools import ToolDefinition
from rag_cli.providers.base import LLMProvider, StreamChunk


class OpenCodeProvider(LLMProvider):
    """Uses opencode CLI to access models like GLM-4.7 via coding plan."""

    def __init__(self, model: str = "zai-coding-plan/glm-4.7"):
        self.model = model

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        # Build the prompt from messages
        prompt_parts = []
        for msg in messages:
            if msg.role == Role.USER:
                prompt_parts.append(msg.content)
            elif msg.role == Role.ASSISTANT:
                prompt_parts.append(f"[Previous response: {msg.content}]")

        prompt = "\n".join(prompt_parts)

        # Call opencode run with the prompt
        proc = await asyncio.create_subprocess_exec(
            "opencode", "run", "--model", self.model, prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise RuntimeError(f"OpenCode error: {error_msg}")

        response = stdout.decode().strip()

        # Yield as single chunk (opencode doesn't stream to us)
        yield StreamChunk(text=response, done=True)

    def count_tokens(self, text: str) -> int:
        # Rough estimate: ~4 chars per token
        return len(text) // 4
