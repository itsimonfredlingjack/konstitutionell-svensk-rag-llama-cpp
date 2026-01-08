"""
SSE Stream Service - Keep-alive wrapper for streaming responses
"""

import asyncio
import json
from typing import AsyncGenerator


class SSEStreamService:
    """Handle SSE streams with automatic keep-alive pings."""

    async def wrap_stream_with_keepalive(
        self,
        event_generator: AsyncGenerator[str, None],
        keepalive_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """
        Wrap an SSE event generator and inject keep-alive pings during idle periods.

        Keep-alive format: ":ping\n\n" (SSE comment line).
        """
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        anext(event_generator),
                        timeout=keepalive_interval,
                    )
                    yield event
                except asyncio.TimeoutError:
                    # No events in interval; send keep-alive comment.
                    yield ":ping\n\n"
        except StopAsyncIteration:
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
