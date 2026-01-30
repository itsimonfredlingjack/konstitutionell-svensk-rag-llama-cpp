import json
from typing import AsyncIterator, List

import httpx

from vibe_cli.models.messages import Message, Role, ToolCall
from vibe_cli.models.tools import ToolDefinition
from vibe_cli.providers.base import LLMProvider, StreamChunk
from vibe_cli.providers.model_switch import select_model_for_messages


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        auto_switch: bool = False,
        small_model: str | None = None,
        large_model: str | None = None,
        switch_tokens: int = 2000,
        switch_keywords: list[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.auto_switch = auto_switch
        self.small_model = small_model
        self.large_model = large_model
        self.switch_tokens = switch_tokens
        self.switch_keywords = switch_keywords or []
        self._tokenizer = None

    async def complete(
        self,
        messages: List[Message],
        tools: List[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        openai_messages = []
        for msg in messages:
            if msg.role == Role.TOOL:
                if msg.tool_results:
                    for r in msg.tool_results:
                        openai_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": r.tool_call_id,
                                "content": r.content,
                            }
                        )
            elif msg.tool_calls:
                openai_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content if isinstance(msg.content, str) else None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
            else:
                openai_messages.append(
                    {
                        "role": msg.role.value,
                        "content": msg.content,
                    }
                )

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
            "messages": openai_messages,
            "stream": True,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = [t.to_openai_schema() for t in tools]

        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        client = httpx.AsyncClient()
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120.0,
            ) as response:
                if response.status_code != 200:
                    # Try to get error details from response body
                    error_body = await response.aread()
                    try:
                        error_data = json.loads(error_body)
                        error_msg = error_data.get("error", {}).get("message", str(error_body[:200]))
                    except json.JSONDecodeError:
                        error_msg = error_body.decode()[:200]
                    raise RuntimeError(f"API error ({response.status_code}): {error_msg}")

                tool_calls_buffer = {}

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    if line.strip() == "data: [DONE]":
                        break

                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    choice = data.get("choices", [{}])[0]
                    delta = choice.get("delta", {})

                    # Text content
                    if content := delta.get("content"):
                        yield StreamChunk(text=content)

                    # Tool calls (streamed incrementally)
                    if tool_calls := delta.get("tool_calls"):
                        for tc in tool_calls:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": "",
                                    "arguments": "",
                                }

                            if tc.get("id"):
                                tool_calls_buffer[idx]["id"] = tc["id"]
                            if func := tc.get("function"):
                                if func.get("name"):
                                    tool_calls_buffer[idx]["name"] = func["name"]
                                if func.get("arguments"):
                                    tool_calls_buffer[idx]["arguments"] += func["arguments"]

                    # Check if done
                    if choice.get("finish_reason"):
                        final_tool_calls = []
                        for tc_data in tool_calls_buffer.values():
                            try:
                                args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                            except json.JSONDecodeError:
                                args = {}
                            final_tool_calls.append(
                                ToolCall(
                                    id=tc_data["id"] or "call_unknown",  # Fallback ID if missing
                                    name=tc_data["name"],
                                    arguments=args,
                                )
                            )

                        yield StreamChunk(
                            done=True,
                            tool_calls=final_tool_calls if final_tool_calls else None,
                            usage=data.get("usage"),
                        )
        finally:
            await client.aclose()

    def count_tokens(self, text: str) -> int:
        if self._tokenizer is None:
            import tiktoken

            try:
                self._tokenizer = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
        return len(self._tokenizer.encode(text))

    async def get_available_models(self) -> List[str]:
        """Fetch available models from the provider."""
        headers = {}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{self.base_url}/models", headers=headers, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    # Handle both standard OpenAI format (data=[...]) and simple list
                    models_data = data.get("data", [])
                    return [m["id"] for m in models_data if "id" in m]
                return []
            except Exception:
                return []
