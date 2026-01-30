"""Tests for ModelRouter."""

from unittest.mock import MagicMock

import pytest

from vibe_cli.providers.router import ModelRouter


@pytest.fixture
def mock_providers():
    """Create mock providers."""
    provider1 = MagicMock()
    provider1.count_tokens.return_value = 10

    provider2 = MagicMock()
    provider2.count_tokens.return_value = 20

    return {"local": provider1, "glm": provider2}


def test_router_init(mock_providers):
    """Test router initialization."""
    router = ModelRouter(mock_providers, "local")

    assert router.current_name == "local"
    assert router.list_providers() == ["local", "glm"]


def test_router_switch(mock_providers):
    """Test switching providers."""
    router = ModelRouter(mock_providers, "local")

    assert router.current_name == "local"

    # Switch to glm
    assert router.switch("glm") is True
    assert router.current_name == "glm"

    # Switch back
    assert router.switch("local") is True
    assert router.current_name == "local"

    # Try invalid provider
    assert router.switch("invalid") is False
    assert router.current_name == "local"  # Unchanged


def test_router_provider_property(mock_providers):
    """Test getting current provider."""
    router = ModelRouter(mock_providers, "local")

    assert router.provider == mock_providers["local"]

    router.switch("glm")
    assert router.provider == mock_providers["glm"]


def test_router_count_tokens(mock_providers):
    """Test token counting delegates to current provider."""
    router = ModelRouter(mock_providers, "local")

    count = router.count_tokens("hello world")

    mock_providers["local"].count_tokens.assert_called_once_with("hello world")
    assert count == 10

    # Switch and count again
    router.switch("glm")
    count = router.count_tokens("test")

    mock_providers["glm"].count_tokens.assert_called_once_with("test")
    assert count == 20


@pytest.mark.asyncio
async def test_router_complete(mock_providers):
    """Test completion delegates to current provider."""
    # Set up async mock
    async def mock_complete(*args, **kwargs):
        yield MagicMock(text="Hello")
        yield MagicMock(text=" World")

    mock_providers["local"].complete = mock_complete

    router = ModelRouter(mock_providers, "local")
    messages = [{"role": "user", "content": "Hi"}]

    chunks = []
    async for chunk in router.complete(messages):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].text == "Hello"
    assert chunks[1].text == " World"
