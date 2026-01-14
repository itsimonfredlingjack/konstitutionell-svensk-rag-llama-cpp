"""Async streaming client for the Constitutional RAG API."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

# Default to local backend, can be overridden via environment
BACKEND_URL = os.environ.get("RAG_BACKEND_URL", "http://localhost:8900")
API_ENDPOINT = f"{BACKEND_URL}/api/constitutional/agent/query/stream"


@dataclass
class Source:
    """A retrieved source document."""

    id: str
    title: str
    score: float
    doc_type: str
    source: str
    snippet: str = ""


@dataclass
class StreamEvent:
    """An event from the RAG stream."""

    type: str  # "sources", "token", "done", "error"
    data: dict | list | str | None = None


class RAGClient:
    """Client for querying the Constitutional RAG API."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        self.base_url = base_url or BACKEND_URL
        self.endpoint = f"{self.base_url}/api/constitutional/agent/query/stream"
        self.timeout = timeout

    async def query(self, question: str, mode: str = "auto") -> AsyncIterator[StreamEvent]:
        """
        Stream a query to the RAG API.

        Yields StreamEvent objects:
        - type="sources": data contains list of Source dicts
        - type="token": data contains text chunk
        - type="done": stream complete
        - type="error": data contains error message
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:  # noqa: SIM117
            async with client.stream(
                "POST",
                self.endpoint,
                json={"question": question, "mode": mode, "history": []},
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status_code != 200:
                    yield StreamEvent(type="error", data=f"HTTP {response.status_code}")
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        if not event_str.strip():
                            continue

                        # Parse SSE format: "data: {...}"
                        for line in event_str.split("\n"):
                            if line.startswith("data:"):
                                json_str = line[5:].strip()
                                try:
                                    data = json.loads(json_str)
                                    yield self._parse_event(data)
                                except json.JSONDecodeError:
                                    continue

    def _parse_event(self, data: dict) -> StreamEvent:
        """Parse a raw event dict into a StreamEvent."""
        event_type = data.get("type", "unknown")

        if event_type == "metadata":
            # Extract sources
            sources = data.get("sources", [])
            return StreamEvent(type="sources", data=sources)

        elif event_type == "token":
            return StreamEvent(type="token", data=data.get("content", ""))

        elif event_type == "done":
            return StreamEvent(type="done", data={"time_ms": data.get("total_time_ms")})

        elif event_type == "error":
            return StreamEvent(type="error", data=data.get("message", "Unknown error"))

        else:
            # Pass through other events (grading, thought_chain, etc.)
            return StreamEvent(type=event_type, data=data)


# Convenience function for simple usage
async def query_rag(question: str, mode: str = "auto") -> AsyncIterator[StreamEvent]:
    """Convenience function to query RAG without instantiating client."""
    client = RAGClient()
    async for event in client.query(question, mode):
        yield event


# Simple test
async def _test():
    """Quick test of the API client."""
    print(f"Testing connection to {API_ENDPOINT}...")
    async for event in query_rag("Vad är GDPR?"):
        if event.type == "sources":
            print(f"Got {len(event.data)} sources")
        elif event.type == "token":
            print(event.data, end="", flush=True)
        elif event.type == "done":
            print(f"\n\nDone in {event.data.get('time_ms', '?')}ms")
        elif event.type == "error":
            print(f"Error: {event.data}")


if __name__ == "__main__":
    asyncio.run(_test())
