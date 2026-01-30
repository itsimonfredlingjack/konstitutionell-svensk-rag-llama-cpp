"""Model router for switching between LLM providers."""

from typing import AsyncIterator

from vibe_cli.models.messages import Message
from vibe_cli.models.tools import ToolDefinition
from vibe_cli.providers.base import LLMProvider, StreamChunk


class ModelRouter:
    """Routes requests to different LLM providers with easy switching."""

    def __init__(self, providers: dict[str, LLMProvider], default: str):
        self.providers = providers
        self.current = default
        self._provider_names = list(providers.keys())

    def switch(self, name: str) -> bool:
        """Switch to a different provider. Returns True if successful."""
        if name in self.providers:
            self.current = name
            return True
        return False

    def list_providers(self) -> list[str]:
        """List available provider names."""
        return self._provider_names

    @property
    def provider(self) -> LLMProvider:
        """Get the current active provider."""
        return self.providers[self.current]

    @property
    def current_name(self) -> str:
        """Get the name of the current provider."""
        return self.current

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Complete using the current provider."""
        async for chunk in self.provider.complete(messages, tools, temperature):
            yield chunk

    def count_tokens(self, text: str) -> int:
        """Count tokens using the current provider."""
        return self.provider.count_tokens(text)
