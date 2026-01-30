import json
from typing import AsyncIterator

import httpx

from vibe_cli.models.messages import Message, Role, ToolCall
from vibe_cli.models.tools import ToolDefinition
from vibe_cli.providers.base import LLMProvider, StreamChunk
from vibe_cli.providers.model_switch import select_model_for_messages


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        auto_switch: bool = False,
        small_model: str | None = None,
        large_model: str | None = None,
        switch_tokens: int = 2000,
        switch_keywords: list[str] | None = None,
        keep_alive: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.auto_switch = auto_switch
        self.small_model = small_model
        self.large_model = large_model
        self.switch_tokens = switch_tokens
        self.switch_keywords = switch_keywords or []
        self.keep_alive = keep_alive

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        payload_messages = _to_ollama_messages(messages)
        selected_model = select_model_for_messages(
            messages=messages,
            default_model=self.model,
            auto_switch=self.auto_switch,
            small_model=self.small_model,
            large_model=self.large_model,
            token_threshold=self.switch_tokens,
            keywords=self.switch_keywords,
            token_counter=self.count_tokens,
        )

        payload = {
            "model": selected_model,
            "messages": payload_messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]

        if self.keep_alive is not None:
            payload["keep_alive"] = self.keep_alive
        elif self.auto_switch:
            payload["keep_alive"] = 0

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120.0,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    raise RuntimeError(f"Ollama error ({response.status_code}): {error_body[:200]}")

                tool_calls: list[ToolCall] = []
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    message = data.get("message", {})
                    content = message.get("content")
                    if content:
                        yield StreamChunk(text=content)

                    if message.get("tool_calls"):
                        tool_calls.extend(_parse_tool_calls(message.get("tool_calls", [])))

                    if data.get("done"):
                        yield StreamChunk(done=True, tool_calls=tool_calls if tool_calls else None)
                        return

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def get_available_models(self) -> list[str]:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            except Exception:
                return []

        if response.status_code != 200:
            return []
        data = response.json()
        models = data.get("models", [])
        return [m.get("name") for m in models if m.get("name")]


def _to_ollama_messages(messages: list[Message]) -> list[dict]:
    payload: list[dict] = []
    for msg in messages:
        if msg.role == Role.TOOL:
            if msg.tool_results:
                for result in msg.tool_results:
                    payload.append(
                        {
                            "role": "tool",
                            "content": result.content,
                        }
                    )
        elif msg.tool_calls:
            payload.append(
                {
                    "role": "assistant",
                    "content": msg.content if isinstance(msg.content, str) else "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": tc.name,
                                "arguments": tc.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
        else:
            payload.append({"role": msg.role.value, "content": msg.content})
    return payload


def _parse_tool_calls(raw_calls: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for idx, call in enumerate(raw_calls):
        func = call.get("function", {})
        name = func.get("name", "")
        args = func.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        calls.append(ToolCall(id=f"call_{idx}", name=name, arguments=args))
    return calls
