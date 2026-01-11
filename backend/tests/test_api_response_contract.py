"""
API response contract tests (no server startup).

Ensures the API response is stable, typed, and never leaks internal fields.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.constitutional_routes import AgentQueryRequest, agent_query
from app.services.guardrail_service import WardenStatus
from app.services.orchestrator_service import RAGPipelineMetrics, RAGResult
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import SearchResult


def _make_result(
    *,
    answer: str,
    mode: ResponseMode,
    sources: list[SearchResult],
    saknas_underlag: bool | None,
    evidence_level: str = "HIGH",
) -> RAGResult:
    metrics = RAGPipelineMetrics()
    metrics.saknas_underlag = saknas_underlag

    return RAGResult(
        answer=answer,
        sources=sources,
        reasoning_steps=[],
        metrics=metrics,
        mode=mode,
        guardrail_status=WardenStatus.UNCHANGED,
        evidence_level=evidence_level,
        success=True,
    )


def _make_orchestrator(result: RAGResult, refusal_text: str) -> Mock:
    orchestrator = Mock()
    orchestrator.process_query = AsyncMock(return_value=result)
    orchestrator.config = Mock()
    orchestrator.config.settings = SimpleNamespace(evidence_refusal_template=refusal_text)
    return orchestrator


@pytest.mark.asyncio
async def test_t1_evidence_success_contract():
    refusal_text = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
    sources = [
        SearchResult(
            id="doc_1",
            title="GDPR Article 6",
            snippet="Article 6 regulates lawful processing of personal data",
            score=0.9,
            source="europa.eu",
            doc_type="law",
            date="2018-05-25",
            retriever="vector_search",
        )
    ]

    result = _make_result(
        answer="Baserat på GDPR Artikel 6...",
        mode=ResponseMode.EVIDENCE,
        sources=sources,
        saknas_underlag=False,
    )

    orchestrator = _make_orchestrator(result, refusal_text)
    request = AgentQueryRequest(question="Vad säger GDPR?", mode="evidence")

    response = await agent_query(request, x_retrieval_strategy=None, orchestrator=orchestrator)
    payload = response.model_dump()
    raw = response.model_dump_json()

    assert set(payload.keys()) == {"answer", "sources", "mode", "saknas_underlag", "evidence_level"}
    assert payload["answer"].startswith("Baserat på GDPR")
    assert payload["mode"] == "evidence"
    assert payload["saknas_underlag"] is False
    assert len(payload["sources"]) == 1
    assert "arbetsanteckning" not in raw
    assert "fakta_utan_kalla" not in raw


@pytest.mark.asyncio
async def test_t2_refusal_contract():
    refusal_text = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
    result = _make_result(
        answer=refusal_text,
        mode=ResponseMode.EVIDENCE,
        sources=[],
        saknas_underlag=True,
    )

    orchestrator = _make_orchestrator(result, refusal_text)
    request = AgentQueryRequest(question="Olagligt ämne?", mode="evidence")

    response = await agent_query(request, x_retrieval_strategy=None, orchestrator=orchestrator)
    payload = response.model_dump()
    raw = response.model_dump_json()

    assert payload["answer"] == refusal_text
    assert payload["saknas_underlag"] is True
    assert payload["sources"] == []
    assert "arbetsanteckning" not in raw


@pytest.mark.asyncio
async def test_t3_malicious_structured_json_sanitized():
    refusal_text = "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats..."
    malicious_answer = (
        '{"mode":"EVIDENCE","saknas_underlag":false,"svar":"Läckage","arbetsanteckning":"INTERNAL"}'
    )

    sources = [
        SearchResult(
            id="doc_2",
            title="Test",
            snippet="Test snippet",
            score=0.7,
            source="test",
            doc_type="law",
            date="2020-01-01",
            retriever="vector_search",
        )
    ]

    result = _make_result(
        answer=malicious_answer,
        mode=ResponseMode.EVIDENCE,
        sources=sources,
        saknas_underlag=False,
    )

    orchestrator = _make_orchestrator(result, refusal_text)
    request = AgentQueryRequest(question="Test?", mode="evidence")

    response = await agent_query(request, x_retrieval_strategy=None, orchestrator=orchestrator)
    payload = response.model_dump()
    raw = response.model_dump_json()

    assert set(payload.keys()) == {"answer", "sources", "mode", "saknas_underlag", "evidence_level"}
    assert payload["answer"] == refusal_text
    assert payload["mode"] == "evidence"
    assert payload["saknas_underlag"] is True
    assert payload["sources"] == []
    assert "arbetsanteckning" not in raw
    assert "fakta_utan_kalla" not in raw
