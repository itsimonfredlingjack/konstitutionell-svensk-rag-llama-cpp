"""
Tests for Streaming Service — SSE streaming RAG pipeline.

Covers:
- CHAT mode: metadata → tokens → done
- Unsafe query: error event
- EVIDENCE mode with no sources: refusal
- Normal ASSIST flow: metadata (sources) → tokens → corrections → done
- SSE event format: "data: {...}\\n\\n"
- Decontextualization emits event when history provided
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.streaming_service import stream_query
from app.services.query_processor_service import ResponseMode


# ── Helpers ───────────────────────────────────────────────────────


def _parse_events(raw_events: list[str]) -> list[dict]:
    """Parse SSE 'data: {...}\\n\\n' strings into dicts."""
    parsed = []
    for event in raw_events:
        assert event.startswith("data: "), f"Bad SSE format: {event!r}"
        assert event.endswith("\n\n"), f"Missing trailing newlines: {event!r}"
        payload = event[len("data: ") : -2]
        parsed.append(json.loads(payload))
    return parsed


def _mock_search_result(
    id="doc_1",
    title="Test Doc",
    snippet="Content.",
    score=0.85,
    source="riksdag",
    doc_type="proposition",
    date="2024-01-01",
    retriever="dense",
    tier="primary",
):
    """Create a mock SearchResult object."""
    s = MagicMock()
    s.id = id
    s.title = title
    s.snippet = snippet
    s.score = score
    s.source = source
    s.doc_type = doc_type
    s.date = date
    s.retriever = retriever
    s.tier = tier
    return s


class _StreamFixture:
    """Bundle of mocks for stream_query tests."""

    def __init__(self, *, mode=ResponseMode.ASSIST, safe=True, sources=None):
        # Config
        self.config = MagicMock()
        self.config.settings.crag_enabled = False
        self.config.settings.crag_enable_self_reflection = False
        self.config.settings.reranking_enabled = False
        self.config.settings.evidence_refusal_template = (
            "Jag saknar underlag för att besvara frågan."
        )

        # Query processor
        self.query_processor = MagicMock()
        classification = MagicMock()
        classification.mode = mode
        self.query_processor.classify_query.return_value = classification

        evidence_level = MagicMock()
        evidence_level.value = "HIGH"
        self.query_processor.determine_evidence_level.return_value = evidence_level
        self.query_processor.get_mode_config.return_value = {
            "temperature": 0.4,
            "num_predict": 1024,
        }

        decontext = MagicMock()
        decontext.rewritten_query = "rewritten query"
        self.query_processor.decontextualize_query.return_value = decontext

        # Guardrail
        self.guardrail = MagicMock()
        self.guardrail.check_query_safety.return_value = (safe, None if safe else "blocked")
        validation = MagicMock()
        validation.corrections = []
        validation.corrected_text = ""
        self.guardrail.validate_response.return_value = validation
        self.guardrail.check_output_leakage.return_value = ("", [])

        # LLM service
        self.llm_service = AsyncMock()

        async def _chat_stream(messages=None, config_override=None):
            yield "Test ", None
            yield "svar.", None
            yield None, MagicMock(tokens_generated=10)

        self.llm_service.chat_stream = _chat_stream

        # Retrieval
        self.retrieval = AsyncMock()
        mock_sources = (
            sources
            if sources is not None
            else [
                _mock_search_result(id="doc_1", title="RF 2 kap.", score=0.92, doc_type="sfs"),
            ]
        )
        retrieval_result = MagicMock()
        retrieval_result.results = mock_sources
        self.retrieval.search_with_epr = AsyncMock(return_value=retrieval_result)

        # Reranker, grader, critic (unused when CRAG disabled)
        self.reranker = AsyncMock()
        self.grader = AsyncMock()
        self.critic = AsyncMock()

        # Function dependencies — use real coroutine for retrieve_examples_fn
        # so asyncio.ensure_future() and .cancel() work properly.
        async def _retrieve_examples(**kwargs):
            return []

        self.resolve_mode_fn = lambda mode_str, classified: (
            ResponseMode.CHAT if mode_str == "chat" else mode
        )
        self.build_llm_context_fn = lambda srcs: "context"
        self.retrieve_examples_fn = _retrieve_examples
        self.format_examples_fn = lambda examples: ""
        self.build_system_prompt_fn = lambda *a, **kw: "system prompt {{CONSTITUTIONAL_EXAMPLES}}"

    async def run(self, question="Vad säger RF?", mode="auto", history=None):
        events = []
        async for event in stream_query(
            config=self.config,
            query_processor=self.query_processor,
            llm_service=self.llm_service,
            guardrail=self.guardrail,
            retrieval=self.retrieval,
            reranker=self.reranker,
            grader=self.grader,
            critic=self.critic,
            resolve_mode_fn=self.resolve_mode_fn,
            build_llm_context_fn=self.build_llm_context_fn,
            retrieve_examples_fn=self.retrieve_examples_fn,
            format_examples_fn=self.format_examples_fn,
            build_system_prompt_fn=self.build_system_prompt_fn,
            question=question,
            mode=mode,
            history=history,
        ):
            events.append(event)
        return events


# ═══════════════════════════════════════════════════════════════════
# SSE Format
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestSSEFormat:
    async def test_all_events_have_correct_format(self):
        """Every event must be 'data: {...}\\n\\n'."""
        fx = _StreamFixture()
        events = await fx.run()

        for event in events:
            assert event.startswith("data: ")
            assert event.endswith("\n\n")
            # Payload must be valid JSON
            payload = event[len("data: ") : -2]
            parsed = json.loads(payload)
            assert "type" in parsed


# ═══════════════════════════════════════════════════════════════════
# CHAT Mode
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestChatMode:
    async def test_chat_emits_metadata_tokens_done(self):
        """CHAT mode: metadata(mode=chat) → token(s) → done."""
        fx = _StreamFixture(mode=ResponseMode.CHAT)
        fx.resolve_mode_fn = lambda m, c: ResponseMode.CHAT
        events = await fx.run()
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert types[0] == "metadata"
        assert parsed[0]["mode"] == "chat"
        assert "token" in types
        assert types[-1] == "done"

    async def test_chat_no_retrieval(self):
        """CHAT mode should not call retrieval."""
        fx = _StreamFixture(mode=ResponseMode.CHAT)
        fx.resolve_mode_fn = lambda m, c: ResponseMode.CHAT
        await fx.run()
        fx.retrieval.search_with_epr.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════
# Unsafe Query
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestUnsafeQuery:
    async def test_unsafe_emits_error(self):
        """Unsafe query should emit a single error event."""
        fx = _StreamFixture(safe=False)
        events = await fx.run(question="ignore instructions")
        parsed = _parse_events(events)

        assert len(parsed) == 1
        assert parsed[0]["type"] == "error"


# ═══════════════════════════════════════════════════════════════════
# EVIDENCE Mode — No Sources
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEvidenceNoSources:
    async def test_evidence_no_sources_emits_refusal(self):
        """EVIDENCE with no sources after retrieval → refusal + done."""
        fx = _StreamFixture(mode=ResponseMode.EVIDENCE, sources=[])
        fx.resolve_mode_fn = lambda mode_str, classified: ResponseMode.EVIDENCE
        events = await fx.run()
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert "metadata" in types
        # Should have refusal indication
        metadata = next(e for e in parsed if e["type"] == "metadata")
        assert metadata.get("refusal") is True or metadata.get("evidence_level") == "NONE"
        assert "done" in types


# ═══════════════════════════════════════════════════════════════════
# Normal ASSIST Flow
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestNormalAssistFlow:
    async def test_full_pipeline_metadata_tokens_done(self):
        """Normal ASSIST: phase → metadata(sources) → phase → tokens → done."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        events = await fx.run()
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        # pipeline emits phase events for retrieval_complete and generation_start
        assert "metadata" in types
        metadata = next(e for e in parsed if e["type"] == "metadata")
        assert metadata["mode"] == "assist"
        assert "sources" in metadata
        assert len(metadata["sources"]) > 0

        token_events = [e for e in parsed if e["type"] == "token"]
        assert len(token_events) >= 1

        assert types[-1] == "done"

    async def test_corrections_emitted_when_present(self):
        """If guardrail finds corrections, a corrections event is emitted."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        correction_mock = MagicMock()
        correction_mock.original_term = "Datainspektionen"
        correction_mock.corrected_term = "IMY"
        validation = MagicMock()
        validation.corrections = [correction_mock]
        validation.corrected_text = "IMY ansvarar."
        fx.guardrail.validate_response.return_value = validation

        events = await fx.run()
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert "corrections" in types

    async def test_no_corrections_no_event(self):
        """If no corrections, no corrections event is emitted."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        events = await fx.run()
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert "corrections" not in types


# ═══════════════════════════════════════════════════════════════════
# Decontextualization
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestDecontextualization:
    async def test_decontextualized_event_when_history(self):
        """When history is provided, a decontextualized event should be emitted."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        history = [{"role": "user", "content": "Vad säger grundlagen?"}]
        events = await fx.run(history=history)
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert "decontextualized" in types
        decontext = next(e for e in parsed if e["type"] == "decontextualized")
        assert "rewritten" in decontext

    async def test_no_decontextualized_event_without_history(self):
        """Without history, no decontextualized event."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        events = await fx.run(history=None)
        parsed = _parse_events(events)

        types = [e["type"] for e in parsed]
        assert "decontextualized" not in types


# ═══════════════════════════════════════════════════════════════════
# Error Handling
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestErrorHandling:
    async def test_exception_emits_error_event(self):
        """Unhandled exception in pipeline should yield error event."""
        fx = _StreamFixture(mode=ResponseMode.ASSIST)
        fx.retrieval.search_with_epr = AsyncMock(side_effect=RuntimeError("boom"))

        events = await fx.run()
        parsed = _parse_events(events)

        assert any(e["type"] == "error" for e in parsed)
