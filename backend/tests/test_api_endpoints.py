"""Unit tests for Constitutional AI API endpoints."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.orchestrator_service import RAGResult, RAGPipelineMetrics
from app.services.query_processor_service import ResponseMode
from app.services.guardrail_service import WardenStatus


class MockSearchResult:
    def __init__(
        self,
        id="doc-001",
        title="Test Document",
        snippet="Test content",
        score=0.95,
        doc_type="test",
        source="test_collection",
        retriever="dense",
        loc=None,
    ):
        self.id = id
        self.title = title
        self.snippet = snippet
        self.score = score
        self.doc_type = doc_type
        self.source = source
        self.retriever = retriever
        self.loc = loc


@pytest.fixture
def mock_rag_result():
    return RAGResult(
        answer="Detta ar ett testsvar om svensk grundlag.",
        sources=[
            MockSearchResult(
                id="doc-001",
                title="RF 2 kap.",
                snippet="Yttrandefrihet",
                score=0.95,
                doc_type="sfs",
                source="riksdag",
            )
        ],
        reasoning_steps=["Query classified as ASSIST"],
        metrics=RAGPipelineMetrics(mode="assist"),
        mode=ResponseMode.ASSIST,
        guardrail_status=WardenStatus.UNCHANGED,
        evidence_level="HIGH",
        success=True,
    )


# ============================================================================
# POST /api/constitutional/agent/query
# ============================================================================


@pytest.mark.unit
async def test_agent_query_happy_path(async_client, mock_orchestrator, mock_rag_result):
    mock_orchestrator.process_query = AsyncMock(return_value=mock_rag_result)
    response = await async_client.post(
        "/api/constitutional/agent/query",
        json={"question": "Vad ar yttrandefrihet?", "mode": "assist"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == mock_rag_result.answer
    assert data["mode"] == "assist"
    assert len(data["sources"]) == 1
    mock_orchestrator.process_query.assert_awaited_once()


@pytest.mark.unit
async def test_agent_query_error_path(async_client, mock_orchestrator):
    from app.core.exceptions import RetrievalError

    mock_orchestrator.process_query = AsyncMock(
        side_effect=RetrievalError("Service temporarily unavailable")
    )
    response = await async_client.post(
        "/api/constitutional/agent/query",
        json={"question": "Test fraga", "mode": "assist"},
    )
    assert response.status_code == 500


@pytest.mark.unit
async def test_agent_query_empty_question(async_client):
    response = await async_client.post(
        "/api/constitutional/agent/query",
        json={"question": "", "mode": "assist"},
    )
    assert response.status_code == 422


# ============================================================================
# POST /api/constitutional/agent/query/stream
# ============================================================================


@pytest.mark.unit
async def test_agent_query_stream_happy_path(async_client, mock_orchestrator):
    async def mock_stream(*args, **kwargs):
        yield "data: " + json.dumps({"type": "metadata", "mode": "assist"}) + "\n\n"
        yield "data: " + json.dumps({"type": "token", "content": "Test"}) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    mock_orchestrator.stream_query = mock_stream
    response = await async_client.post(
        "/api/constitutional/agent/query/stream",
        json={"question": "Vad ar yttrandefrihet?", "mode": "assist"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "metadata" in response.text


@pytest.mark.unit
async def test_agent_query_stream_error_event(async_client, mock_orchestrator):
    async def mock_error_stream(*args, **kwargs):
        yield "data: " + json.dumps({"type": "error", "message": "LLM timeout"}) + "\n\n"

    mock_orchestrator.stream_query = mock_error_stream
    response = await async_client.post(
        "/api/constitutional/agent/query/stream",
        json={"question": "Test fraga", "mode": "assist"},
    )
    assert response.status_code == 200
    assert "error" in response.text


@pytest.mark.unit
async def test_agent_query_stream_long_query_rejected(async_client):
    response = await async_client.post(
        "/api/constitutional/agent/query/stream",
        json={"question": "A" * 2001, "mode": "assist"},
    )
    assert response.status_code == 422


# ============================================================================
# GET /api/constitutional/health
# ============================================================================


@pytest.mark.unit
async def test_health_check_healthy(async_client, mock_orchestrator):
    mock_orchestrator.health_check = AsyncMock(return_value=True)
    mock_orchestrator.get_status = MagicMock(
        return_value={
            "orchestrator": "initialized",
            "llm_service": "initialized",
        }
    )
    response = await async_client.get("/api/constitutional/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert isinstance(data["services"], dict)


@pytest.mark.unit
async def test_health_check_degraded(async_client, mock_orchestrator):
    mock_orchestrator.health_check = AsyncMock(return_value=False)
    mock_orchestrator.get_status = MagicMock(return_value={"orchestrator": "initialized"})
    response = await async_client.get("/api/constitutional/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


@pytest.mark.unit
async def test_health_check_idempotent(async_client, mock_orchestrator):
    mock_orchestrator.health_check = AsyncMock(return_value=True)
    mock_orchestrator.get_status = MagicMock(return_value={"orchestrator": "initialized"})
    r1 = await async_client.get("/api/constitutional/health")
    r2 = await async_client.get("/api/constitutional/health")
    assert r1.status_code == r2.status_code == 200


# ============================================================================
# GET /api/documents
# ============================================================================


@pytest.mark.unit
async def test_documents_list_happy_path(async_client, mock_retrieval_service):
    mock_coll = MagicMock()
    mock_coll.name = "test_collection"
    mock_coll.count = MagicMock(return_value=2)
    mock_coll.metadata = None
    mock_coll.get = MagicMock(
        return_value={
            "ids": ["doc-001", "doc-002"],
            "documents": ["Content 1", "Content 2"],
            "metadatas": [{"title": "Doc 1"}, {"title": "Doc 2"}],
        }
    )
    mock_retrieval_service._chromadb_client = MagicMock()
    mock_retrieval_service._chromadb_client.list_collections = MagicMock(return_value=[mock_coll])
    response = await async_client.get("/api/documents?page=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) == 2


@pytest.mark.unit
async def test_documents_list_uninitialized(async_client, mock_retrieval_service):
    mock_retrieval_service._chromadb_client = None
    response = await async_client.get("/api/documents")
    assert response.status_code == 500


@pytest.mark.unit
async def test_documents_list_empty(async_client, mock_retrieval_service):
    mock_retrieval_service._chromadb_client = MagicMock()
    mock_retrieval_service._chromadb_client.list_collections = MagicMock(return_value=[])
    response = await async_client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


# ============================================================================
# POST /api/documents
# ============================================================================


@pytest.mark.unit
async def test_documents_create_happy_path(async_client, mock_retrieval_service):
    mock_coll = MagicMock()
    mock_coll.add = MagicMock()
    mock_coll.get = MagicMock(return_value={"ids": []})
    mock_retrieval_service._chromadb_client = MagicMock()
    mock_retrieval_service._chromadb_client.get_collection = MagicMock(return_value=mock_coll)
    response = await async_client.post(
        "/api/documents",
        json={"content": "All offentlig makt utgar fran folket.", "collection": "testcoll"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["collection"] == "testcoll"


@pytest.mark.unit
async def test_documents_create_invalid_collection(async_client):
    response = await async_client.post(
        "/api/documents",
        json={"content": "Some content", "collection": "invalid$name!"},
    )
    assert response.status_code == 422


@pytest.mark.unit
async def test_documents_create_missing_content(async_client):
    response = await async_client.post(
        "/api/documents",
        json={"collection": "test_collection"},
    )
    assert response.status_code == 422
