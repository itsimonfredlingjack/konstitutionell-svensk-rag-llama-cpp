"""
Constitutional AI Dashboard API Routes v2
Refactored with Service Layer Architecture
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Request, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Import services
from ..core.rate_limiter import limiter
from ..services.orchestrator_service import OrchestratorService, get_orchestrator_service
from ..services.rag_models import RAGResult
from ..services.retrieval_service import RetrievalStrategy

router = APIRouter(prefix="/api/constitutional", tags=["constitutional"])
logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════
# SECURITY VIOLATION RATE LIMITING
# ═════════════════════════════════════════════════════════════════════════

_security_violations: dict[str, list[float]] = defaultdict(list)
_ip_bans: dict[str, float] = {}

SECURITY_VIOLATION_LIMIT = 3
SECURITY_VIOLATION_WINDOW = 300  # 5 minutes
SECURITY_BAN_DURATION = 900  # 15 minutes


def check_security_ban(ip: str) -> bool:
    """Check if IP is banned due to repeated security violations."""
    now = time.time()
    if ip in _ip_bans:
        if now < _ip_bans[ip]:
            return True
        del _ip_bans[ip]
    if ip in _security_violations:
        recent = [t for t in _security_violations[ip] if now - t < SECURITY_VIOLATION_WINDOW]
        _security_violations[ip] = recent
        if len(recent) >= SECURITY_VIOLATION_LIMIT:
            _ip_bans[ip] = now + SECURITY_BAN_DURATION
            return True
    return False


def record_security_violation(ip: str) -> None:
    """Record a security violation for an IP address."""
    _security_violations[ip].append(time.time())


# ═════════════════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═════════════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    status: str
    services: Dict[str, str]
    timestamp: str


class ServiceCheck(BaseModel):
    """Health check result for a single service."""

    status: str  # "ok", "degraded", "error"
    details: Optional[Dict[str, Any]] = None


class ReadinessResponse(BaseModel):
    """Deep readiness check response with dependency status."""

    status: str  # "ready" or "not_ready"
    checks: Dict[str, ServiceCheck]
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


class MetricsResponse(BaseModel):
    """RAG pipeline metrics response."""

    total_requests: int
    total_saknas_underlag: int
    total_parse_errors: int
    saknas_underlag_rate: float
    parse_error_rate: float
    requests_last_1min: int
    requests_last_5min: int
    requests_last_1hour: int
    mode_breakdown: Dict[str, int]
    top_saknas_questions: List[str]
    top_error_questions: List[str]


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
    If the answer is structured JSON with a "svar" field, extract it.

    Returns:
        (sanitized_answer, saknas_underlag_override, was_sanitized)
    """
    if answer is None:
        answer = ""

    looks_like_json = _looks_like_structured_json(answer)
    contains_internal = "arbetsanteckning" in answer or "fakta_utan_kalla" in answer

    if looks_like_json or contains_internal:
        # Try to extract "svar" from the structured JSON before discarding
        import json as _json

        try:
            parsed = _json.loads(answer.strip())
            svar = parsed.get("svar", "").strip()
            if svar and len(svar) > 20:
                # Successfully extracted answer from leaked JSON
                return svar, parsed.get("saknas_underlag", False), False
        except (ValueError, TypeError, AttributeError):
            pass

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


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Deep readiness check with dependency verification.

    Verifies:
    - ChromaDB connection and collections
    - LLM service availability and model status
    - Embedding service status

    Returns detailed status for each dependency.
    """
    checks = {}
    all_ready = True

    try:
        # Check ChromaDB via retrieval service
        if hasattr(orchestrator, "retrieval") and orchestrator.retrieval:
            try:
                chromadb_healthy = await orchestrator.retrieval.health_check()
                if chromadb_healthy and hasattr(orchestrator.retrieval, "_chromadb_client"):
                    client = orchestrator.retrieval._chromadb_client
                    if client:
                        collections = (
                            client.list_collections() if hasattr(client, "list_collections") else []
                        )
                        checks["chromadb"] = ServiceCheck(
                            status="ok",
                            details={"collections": len(collections) if collections else 0},
                        )
                    else:
                        checks["chromadb"] = ServiceCheck(
                            status="error", details={"error": "Client not initialized"}
                        )
                        all_ready = False
                else:
                    checks["chromadb"] = ServiceCheck(
                        status="degraded", details={"healthy": chromadb_healthy}
                    )
                    all_ready = False
            except Exception as e:
                checks["chromadb"] = ServiceCheck(status="error", details={"error": str(e)})
                all_ready = False
        else:
            checks["chromadb"] = ServiceCheck(
                status="error", details={"error": "Retrieval service not available"}
            )
            all_ready = False
    except Exception as e:
        checks["chromadb"] = ServiceCheck(status="error", details={"error": str(e)})
        all_ready = False

    try:
        # Check LLM service
        if hasattr(orchestrator, "llm_service") and orchestrator.llm_service:
            try:
                llm_healthy = await orchestrator.llm_service.health_check()
                model_name = getattr(
                    orchestrator.config.settings,
                    "constitutional_model",
                    "unknown",
                )
                if llm_healthy:
                    checks["llm_service"] = ServiceCheck(status="ok", details={"model": model_name})
                else:
                    checks["llm_service"] = ServiceCheck(
                        status="degraded", details={"model": model_name}
                    )
                    all_ready = False
            except Exception as e:
                checks["llm_service"] = ServiceCheck(status="error", details={"error": str(e)})
                all_ready = False
        else:
            checks["llm_service"] = ServiceCheck(
                status="error", details={"error": "LLM service not available"}
            )
            all_ready = False
    except Exception as e:
        checks["llm_service"] = ServiceCheck(status="error", details={"error": str(e)})
        all_ready = False

    try:
        # Check embedding service via retrieval
        if hasattr(orchestrator, "retrieval") and orchestrator.retrieval:
            if hasattr(orchestrator.retrieval, "_embedding_service"):
                embedding_svc = orchestrator.retrieval._embedding_service
                if embedding_svc and hasattr(embedding_svc, "is_initialized"):
                    if embedding_svc.is_initialized:
                        checks["embedding_service"] = ServiceCheck(status="ok", details={})
                    else:
                        checks["embedding_service"] = ServiceCheck(
                            status="error", details={"error": "Not initialized"}
                        )
                        all_ready = False
                else:
                    checks["embedding_service"] = ServiceCheck(status="degraded", details={})
            else:
                checks["embedding_service"] = ServiceCheck(status="unknown", details={})
        else:
            checks["embedding_service"] = ServiceCheck(
                status="error", details={"error": "Retrieval service not available"}
            )
            all_ready = False
    except Exception as e:
        checks["embedding_service"] = ServiceCheck(status="error", details={"error": str(e)})
        all_ready = False

    return ReadinessResponse(
        status="ready" if all_ready else "not_ready",
        checks=checks,
        timestamp=datetime.now().isoformat(),
    )


@router.get("/metrics", response_model=MetricsResponse)
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
    full_metrics = metrics.get_full_metrics()

    return MetricsResponse(**full_metrics)


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
async def get_collections(
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Get list of ChromaDB collections with metadata.
    Returns CollectionInfo list for frontend.
    """
    try:
        # Access the initialized retrieval service via orchestrator
        if not hasattr(orchestrator, "retrieval") or not orchestrator.retrieval:
            return []
        client = orchestrator.retrieval._chromadb_client
        if not client:
            return []

        collections = client.list_collections()
        result = []
        for coll in collections:
            # Skip leftover test collections
            if coll.name.startswith("test_"):
                continue
            try:
                result.append(
                    CollectionInfo(
                        name=coll.name,
                        document_count=coll.count(),
                        metadata_fields=list(coll.metadata.get("metadata_fields", []))
                        if coll.metadata
                        else [],
                    )
                )
            except Exception:
                # Skip collections that fail to count (e.g. corrupted)
                continue
        return result
    except Exception as e:
        logger.warning(f"Failed to list collections: {e}")
        return []


@router.post("/agent/query", response_model=AgentQueryResponse)
@limiter.limit("30/minute")
async def agent_query(
    request: Request,
    body: AgentQueryRequest,
    x_retrieval_strategy: Optional[str] = Header(default=None, alias="X-Retrieval-Strategy"),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Full agentic RAG pipeline using OrchestratorService.
    """
    try:
        # Security ban check
        client_ip = request.client.host if request.client else "unknown"
        if check_security_ban(client_ip):
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "För många säkerhetsöverträdelser. Försök igen senare.",
                },
            )

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
        history = [{"role": msg.role, "content": msg.content} for msg in body.history or []]

        # Process query via OrchestratorService
        result: RAGResult = await orchestrator.process_query(
            question=body.question,
            mode=body.mode,
            k=10,
            retrieval_strategy=retrieval_strategy,
            history=history,
            use_agent=body.use_agent,  # NEW: Pass agent flag
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
            pass  # Preserve retrieved sources even when answer is sanitized

        # Record security violations for rate limiting
        if not result.success and result.error and "security" in result.error.lower():
            record_security_violation(client_ip)

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
@limiter.limit("20/minute")
async def agent_query_stream(
    request: Request,
    body: AgentQueryRequest,
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

    # Security ban check
    client_ip = request.client.host if request.client else "unknown"
    if check_security_ban(client_ip):
        import json

        async def banned_response():
            yield f"data: {json.dumps({'type': 'error', 'error': 'För många säkerhetsöverträdelser. Försök igen senare.'})}\n\n"

        return StreamingResponse(
            banned_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

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
    history = [{"role": msg.role, "content": msg.content} for msg in body.history or []]

    # Stream via OrchestratorService
    async def generate():
        async for event in orchestrator.stream_query(
            question=body.question,
            mode=body.mode,
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
