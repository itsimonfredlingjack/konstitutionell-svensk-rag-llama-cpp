"""Provider that talks to the Constitutional AI FastAPI backend via SSE."""

import json
from typing import AsyncIterator

import httpx

from rag_cli.providers.base import StreamChunk


class RAGBackendProvider:
    """Sends queries to the Constitutional AI backend and streams SSE responses."""

    def __init__(
        self,
        base_url: str = "http://localhost:8900",
        endpoint: str = "/api/constitutional/agent/query/stream",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout = timeout
        self.history: list[dict] = []

    async def query(self, question: str, mode: str = "auto") -> AsyncIterator[StreamChunk]:
        """Send question to backend and yield streamed chunks."""
        payload = {
            "question": question,
            "mode": mode,
            "history": self.history[-10:],
        }

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}{self.endpoint}",
                json=payload,
                timeout=self.timeout,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield StreamChunk(
                        text=f"Backend error ({response.status_code}): {error_body.decode()[:200]}",
                        done=True,
                    )
                    return

                async for line in response.aiter_lines():
                    chunk = self._parse_sse_line(line)
                    if chunk is not None:
                        yield chunk
                        if chunk.done:
                            return

    def _parse_sse_line(self, line: str) -> StreamChunk | None:
        """Parse a single SSE line into a StreamChunk or None."""
        if not line.startswith("data: "):
            return None

        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            return None

        event_type = data.get("type", "")

        if event_type == "token":
            return StreamChunk(text=data.get("content", ""))
        elif event_type == "metadata":
            return StreamChunk(metadata=data)
        elif event_type == "done":
            return StreamChunk(done=True)
        elif event_type == "error":
            return StreamChunk(text=f"\n[Error: {data.get('message', 'Unknown')}]", done=True)

        return None

    def add_to_history(self, role: str, content: str) -> None:
        """Track conversation history for multi-turn."""
        self.history.append({"role": role, "content": content})
        if len(self.history) > 20:
            self.history = self.history[-20:]
