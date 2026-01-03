"""
Constitutional AI Dashboard API Routes v2
Refactored with Service Layer Architecture
"""

import asyncio
from fastapi import APIRouter, HTTPException, Query, Header, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Import services
from app.services.orchestrator_service import OrchestratorService, get_orchestrator_service, RAGResult
from app.services.retrieval_service import RetrievalService, get_retrieval_service, RetrievalStrategy
from app.services.config_service import ConfigService, get_config_service

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
        default=None,
        description="Conversation history for context (max 10 messages)"
    )


class AgentSource(BaseModel):
    id: str
    title: str
    snippet: str
    score: float
    doc_type: Optional[str] = None
    source: str


class AgentQueryResponse(BaseModel):
    answer: str
    sources: List[AgentSource]
    reasoning_steps: List[str]
    model_used: str
    total_time_ms: int
    mode: str
    warden_status: str
    evidence_level: str
    corrections_applied: List[str]


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
        timestamp=datetime.now().isoformat()
    )


@router.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(
    request: AgentQueryRequest,
    x_retrieval_strategy: Optional[str] = Header(default=None, alias="X-Retrieval-Strategy"),
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
):
    """
    Full agentic RAG pipeline using OrchestratorService.
    
    Pipeline:
    1. Query classification (CHAT/ASSIST/EVIDENCE)
    2. Query decontextualization (if history provided)
    3. Document retrieval (Phase 1-4 RetrievalOrchestrator)
    4. LLM generation (Ministral 3 14B)
    5. Guardrail validation (Jail Warden v2)
    6. Evidence level assignment
    
    Response modes:
    - CHAT: Direct LLM response, no sources
    - ASSIST: Search + LLM with conversational tone
    - EVIDENCE: Search + LLM with formal tone and citations
    
    Headers:
    - X-Retrieval-Strategy: "parallel_v1" (default) | "rewrite_v1" | "rag_fusion" | "adaptive"
    """
    try:
        # Map header to RetrievalStrategy
        strategy_map = {
            "parallel_v1": RetrievalStrategy.PARALLEL_V1,
            "rewrite_v1": RetrievalStrategy.REWRITE_V1,
            "rag_fusion": RetrievalStrategy.RAG_FUSION,
            "adaptive": RetrievalStrategy.ADAPTIVE,
        }
        retrieval_strategy = strategy_map.get(x_retrieval_strategy, RetrievalStrategy.PARALLEL_V1)
        
        # Convert history for OrchestratorService
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history or []
        ]
        
        # Process query via OrchestratorService
        result: RAGResult = await orchestrator.process_query(
            question=request.question,
            mode=request.mode,
            k=10,
            retrieval_strategy=retrieval_strategy,
            history=history,
        )
        
        # Convert to response format
        return AgentQueryResponse(
            answer=result.answer,
            sources=[
                AgentSource(
                    id=s.id,
                    title=s.title,
                    snippet=s.snippet,
                    score=s.score,
                    doc_type=s.doc_type,
                    source=s.source
                )
                for s in result.sources
            ],
            reasoning_steps=result.reasoning_steps,
            model_used=result.metrics.model_used,
            total_time_ms=int(result.metrics.total_pipeline_ms),
            mode=result.mode.value,
            warden_status=result.guardrail_status.value,
            evidence_level=result.evidence_level,
            corrections_applied=[f"{c.original_term} → {c.corrected_term}" for c in result.guardrail_result.corrections] if hasattr(result, 'guardrail_result') else []
        )
    
    except Exception as e:
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
    retrieval_strategy = strategy_map.get(x_retrieval_strategy, RetrievalStrategy.PARALLEL_V1)
    
    # Convert history for OrchestratorService
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in request.history or []
    ]
    
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
        }
    )


# ═════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═════════════════════════════════════════════════════════════════════════

# Import at module level (added to avoid FastAPI dependency issues)
from fastapi import WebSocket

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
    except Exception as e:
        await websocket.close()
    finally:
        pass

