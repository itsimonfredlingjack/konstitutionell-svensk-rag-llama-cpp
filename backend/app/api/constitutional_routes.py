"""
Constitutional AI Dashboard API Routes v2
Refactored with Service Layer Architecture
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Header, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import services
from ..services.orchestrator_service import OrchestratorService, RAGResult, get_orchestrator_service
from ..services.retrieval_service import RetrievalStrategy, get_retrieval_service

router = APIRouter(prefix="/api/constitutional", tags=["constitutional"])


# ═════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═════════════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]
    timestamp: str


class OverviewStats(BaseModel):
    total_documents: int
    collections: Dict[str, int]
    storage_size_mb: float
    last_updated: str


class DocumentTypeStats(BaseModel):
    doc_type: str
    count: int
    percentage: float


class TimelineDataPoint(BaseModel):
    date: str
    count: int


class CollectionInfo(BaseModel):
    name: str
    document_count: int
    metadata_fields: List[str]


class SearchFilters(BaseModel):
    doc_type: Optional[str] = None
    source: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    filters: Optional[SearchFilters] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=100)
    sort: str = Field(default="relevance")


class SearchResult(BaseModel):
    id: str
    title: str
    source: str
    doc_type: Optional[str] = None
    snippet: str
    score: float
    date: Optional[str] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    page: int
    limit: int
    query: str


# ═════════════════════════════════════════════════════════════════════════
# AGENTIC RAG MODELS
# ═════════════════════════════════════════════════════════════════════════


class ConversationMessage(BaseModel):
    """A message in conversation history."""

    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    mode: str = Field(default="auto", description="Query mode: auto, chat, assist, evidence")
    history: Optional[List[ConversationMessage]] = Field(
        default=None, description="Conversation history for context (max 10 messages)"
    )
    use_agent: bool = Field(
        default=False, description="Use LangGraph agentic flow instead of linear pipeline"
    )


class SourceItem(BaseModel):
    id: str
    title: str
    snippet: str
    score: Optional[float] = None
    doc_type: Optional[str] = None
    source: Optional[str] = None
    retriever: Optional[str] = None
    loc: Optional[str] = None


class CitationItem(BaseModel):
    """Citation linking a claim to its source."""

    claim: str
    source_id: str
    source_title: str
    source_collection: str
    tier: str


class RoutingInfo(BaseModel):
    """EPR routing configuration used for a query."""

    primary: List[str] = []
    support: List[str] = []
    secondary: List[str] = []
    secondary_budget: int = 0


class AgentQueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    mode: str
    saknas_underlag: bool
    evidence_level: Optional[str] = None
    citations: List[CitationItem] = []
    intent: Optional[str] = None
    routing: Optional[RoutingInfo] = None


def _looks_like_structured_json(answer: str) -> bool:
    stripped = answer.lstrip()
    return stripped.startswith("{") and '"mode"' in stripped and '"svar"' in stripped


def _sanitize_answer(
    answer: str,
    mode_value: str,
    refusal_text: str,
    safe_fallback: str,
) -> tuple[str, bool, bool]:
    """
    Sanitize answer to avoid leaking structured JSON or internal fields.

    Returns:
        (sanitized_answer, saknas_underlag_override, was_sanitized)
    """
    if answer is None:
        answer = ""

    looks_like_json = _looks_like_structured_json(answer)
    contains_internal = "arbetsanteckning" in answer or "fakta_utan_kalla" in answer

    if looks_like_json or contains_internal:
        if mode_value == "evidence":
            return refusal_text, True, True
        return safe_fallback, False, True

    return answer, False, False


# ═════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════


@router.get("/health", response_model=HealthResponse)
async def health_check(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Health check for Constitutional AI services.
    Returns Orchestrator status and child service health.
    """
    status = await orchestrator.health_check()
    service_status = orchestrator.get_status()

    return HealthResponse(
        status="healthy" if status else "degraded",
        services=service_status,
        timestamp=datetime.now().isoformat(),
    )


@router.get("/metrics")
async def get_rag_metrics_endpoint():
    """
    Get RAG pipeline metrics for observability.

    Returns:
        - Lifetime totals for requests, saknas_underlag, and parse_errors
        - Rates for last 1min, 5min, and 1hour windows
        - Breakdown by response mode
        - Top questions triggering saknas_underlag and parse_errors
    """
    from ..utils.metrics import get_rag_metrics

    metrics = get_rag_metrics()
    return metrics.get_full_metrics()


@router.get("/metrics/prometheus")
async def get_prometheus_metrics():
    """
    Export metrics in Prometheus text exposition format.

    Can be scraped by Prometheus server at /api/constitutional/metrics/prometheus
    """
    from fastapi.responses import PlainTextResponse
    from ..utils.metrics import get_rag_metrics

    metrics = get_rag_metrics()
    return PlainTextResponse(
        content=metrics.to_prometheus_format(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/stats/overview", response_model=OverviewStats)
async def get_stats_overview():
    """
    Placeholder for dashboard statistics to satisfy frontend requirements.
    Returns OverviewStats format matching frontend expectations.
    """
    return OverviewStats(
        total_documents=0,
        collections={},
        storage_size_mb=0.0,
        last_updated=datetime.now().isoformat(),
    )


@router.get("/collections", response_model=List[CollectionInfo])
async def get_collections():
    """
    Get list of ChromaDB collections with metadata.
    Returns CollectionInfo list for frontend.
    """
    try:
        # Get retrieval service directly
        retrieval = get_retrieval_service()
        client = retrieval._chromadb_client
        if not client:
            return []

        collections = client.list_collections()
        result = []
        for coll in collections:
            result.append(
                CollectionInfo(
                    name=coll.name,
                    document_count=coll.count(),
                    metadata_fields=list(coll.metadata.get("metadata_fields", []))
                    if coll.metadata
                    else [],
                )
            )
        return result
    except Exception:
        return []


@router.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(
    request: AgentQueryRequest,
    x_retrieval_strategy: Optional[str] = Header(default=None, alias="X-Retrieval-Strategy"),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Full agentic RAG pipeline using OrchestratorService.
    """
    try:
        # Map header to RetrievalStrategy
        strategy_map = {
            "parallel_v1": RetrievalStrategy.PARALLEL_V1,
            "rewrite_v1": RetrievalStrategy.REWRITE_V1,
            "rag_fusion": RetrievalStrategy.RAG_FUSION,
            "adaptive": RetrievalStrategy.ADAPTIVE,
        }

        # FIX: Säkra upp None-värde innan lookup
        strategy_key = x_retrieval_strategy or "parallel_v1"
        retrieval_strategy = strategy_map.get(strategy_key, RetrievalStrategy.PARALLEL_V1)

        # Convert history for OrchestratorService
        history = [{"role": msg.role, "content": msg.content} for msg in request.history or []]

        # Process query via OrchestratorService
        result: RAGResult = await orchestrator.process_query(
            question=request.question,
            mode=request.mode,
            k=10,
            retrieval_strategy=retrieval_strategy,
            history=history,
            use_agent=request.use_agent,  # NEW: Pass agent flag
        )

        mode_value = result.mode.value if hasattr(result.mode, "value") else str(result.mode)
        refusal_text = getattr(
            orchestrator.config.settings,
            "evidence_refusal_template",
            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
        )
        safe_fallback = "Jag kunde inte tolka modellens svar. Försök igen."

        answer, saknas_override, was_sanitized = _sanitize_answer(
            result.answer,
            mode_value,
            refusal_text,
            safe_fallback,
        )

        # Determine saknas_underlag
        saknas_underlag = getattr(result.metrics, "saknas_underlag", None)
        if was_sanitized:
            saknas_underlag = saknas_override
        elif saknas_underlag is None:
            if mode_value == "evidence" and refusal_text in answer:
                saknas_underlag = True
            else:
                saknas_underlag = False

        # Ensure non-empty answer
        if not answer.strip():
            if mode_value == "evidence":
                answer = refusal_text
                saknas_underlag = True
            else:
                answer = safe_fallback
                saknas_underlag = False

        # Sources: only from orchestrator result, but empty on refusal/sanitized fallback
        sources = result.sources or []

        # GUARDRAIL: In EVIDENCE mode, if evidence_level is NONE and no sources,
        # the system MUST refuse — never return a hallucinated answer
        evidence_level_str = (result.evidence_level or "NONE").upper()
        if mode_value == "evidence" and evidence_level_str == "NONE" and not sources:
            answer = refusal_text
            saknas_underlag = True

        if mode_value == "evidence" and saknas_underlag:
            sources = []
        if was_sanitized and mode_value == "assist":
            sources = []

        # Convert to response format (no internal fields)
        return AgentQueryResponse(
            answer=answer,
            sources=[
                SourceItem(
                    id=s.id,
                    title=s.title,
                    snippet=s.snippet,
                    score=s.score,
                    doc_type=s.doc_type,
                    source=s.source,
                    retriever=getattr(s, "retriever", None),
                    loc=getattr(s, "loc", None),
                )
                for s in sources
            ],
            mode=mode_value,
            saknas_underlag=bool(saknas_underlag),
            evidence_level=result.evidence_level,
        )

    except Exception:
        # Will be caught by global exception handler
        raise


@router.post("/agent/query/stream")
async def agent_query_stream(
    request: AgentQueryRequest,
    x_retrieval_strategy: Optional[str] = Header(default=None, alias="X-Retrieval-Strategy"),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Streaming version of agent query using OrchestratorService.

    Returns Server-Sent Events (SSE) with real-time response.

    Events:
    - {type: "metadata", mode: "ASSIST", sources: [...], evidence_level: "HIGH"}
    - {type: "decontextualized", original: "...", rewritten: "..."}
    - {type: "token", content: "..."}  (repeated for each token)
    - {type: "corrections", corrections: [...], corrected_text: "..."}
    - {type: "done", total_time_ms: 1234}
    - {type: "error", message: "..."}

    Frontend should use EventSource or fetch with streaming body.
    """

    # Map header to RetrievalStrategy
    strategy_map = {
        "parallel_v1": RetrievalStrategy.PARALLEL_V1,
        "rewrite_v1": RetrievalStrategy.REWRITE_V1,
        "rag_fusion": RetrievalStrategy.RAG_FUSION,
        "adaptive": RetrievalStrategy.ADAPTIVE,
    }
    # Default to ADAPTIVE for better förkortningsexpansion och query understanding
    retrieval_key = x_retrieval_strategy or "adaptive"
    retrieval_strategy = strategy_map.get(retrieval_key, RetrievalStrategy.ADAPTIVE)

    # Convert history for OrchestratorService
    history = [{"role": msg.role, "content": msg.content} for msg in request.history or []]

    # Stream via OrchestratorService
    async def generate():
        async for event in orchestrator.stream_query(
            question=request.question,
            mode=request.mode,
            k=10,
            retrieval_strategy=retrieval_strategy,
            history=history,
        ):
            yield event

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ═════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════


async def harvest_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for live harvest progress updates.
    Constitutional AI document harvesting status.
    """
    await websocket.accept()
    try:
        while True:
            # Send keepalive heartbeat
            await websocket.send_json({"type": "heartbeat", "status": "connected"})
            await asyncio.sleep(30)
    except Exception:
        await websocket.close()
    finally:
        pass
