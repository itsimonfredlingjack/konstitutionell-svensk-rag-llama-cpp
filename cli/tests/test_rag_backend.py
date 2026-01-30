"""Tests for the RAG backend SSE provider."""

import pytest

from rag_cli.providers.rag_backend import RAGBackendProvider


@pytest.fixture
def provider():
    return RAGBackendProvider(base_url="http://localhost:8900")


def test_provider_init(provider):
    assert provider.base_url == "http://localhost:8900"
    assert provider.endpoint == "/api/constitutional/agent/query/stream"
    assert provider.history == []


def test_parse_token_event(provider):
    chunk = provider._parse_sse_line('data: {"type": "token", "content": "Hello"}')
    assert chunk is not None
    assert chunk.text == "Hello"
    assert chunk.done is False


def test_parse_metadata_event(provider):
    line = 'data: {"type": "metadata", "mode": "ASSIST", "sources": [{"id": "1", "title": "SFS", "snippet": "...", "score": 0.85}], "evidence_level": "HIGH"}'
    chunk = provider._parse_sse_line(line)
    assert chunk is not None
    assert chunk.metadata is not None
    assert chunk.metadata["mode"] == "ASSIST"
    assert len(chunk.metadata["sources"]) == 1


def test_parse_done_event(provider):
    chunk = provider._parse_sse_line('data: {"type": "done", "total_time_ms": 1234}')
    assert chunk is not None
    assert chunk.done is True


def test_parse_error_event(provider):
    chunk = provider._parse_sse_line('data: {"type": "error", "message": "LLM timeout"}')
    assert chunk is not None
    assert "LLM timeout" in chunk.text
    assert chunk.done is True


def test_parse_non_data_line(provider):
    assert provider._parse_sse_line("event: ping") is None
    assert provider._parse_sse_line("") is None
    assert provider._parse_sse_line(": comment") is None


def test_parse_invalid_json(provider):
    assert provider._parse_sse_line("data: not-json") is None


def test_history_tracking(provider):
    provider.add_to_history("user", "Hello")
    provider.add_to_history("assistant", "Hi there")
    assert len(provider.history) == 2
    assert provider.history[0] == {"role": "user", "content": "Hello"}


def test_history_limit(provider):
    for i in range(25):
        provider.add_to_history("user", f"msg {i}")
    assert len(provider.history) == 20
    assert provider.history[0] == {"role": "user", "content": "msg 5"}
