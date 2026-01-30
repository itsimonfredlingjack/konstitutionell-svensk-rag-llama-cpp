from unittest.mock import AsyncMock, MagicMock

import pytest

from vibe_cli.models.messages import Message, Role
from vibe_cli.providers.openai_compat import OpenAICompatProvider


@pytest.mark.asyncio
async def test_openai_complete():
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200

    async def lines_generator():
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
            'data: {"choices": [{"finish_reason": "stop"}]}',
            'data: [DONE]'
        ]
        for line in lines:
            yield line

    mock_response.aiter_lines.return_value = lines_generator()
    mock_response.raise_for_status = MagicMock()

    # Mock httpx client
    mock_client = MagicMock()
    # Mock stream to return an async context manager that yields mock_response
    mock_client.stream.return_value.__aenter__.return_value = mock_response
    mock_client.aclose = AsyncMock()

    # Patch httpx.AsyncClient to return our mock client when instantiated
    with pytest.MonkeyPatch.context() as m:
        m.setattr("httpx.AsyncClient", lambda: mock_client)

        provider = OpenAICompatProvider(api_key="test")
        chunks = []
        async for chunk in provider.complete(messages=[Message(role=Role.USER, content="Hi")]):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].text == "Hello"
        assert chunks[1].text == " world"
        assert chunks[2].done is True
