"""
Retrieval Service - ChromaDB Wrapper with Advanced Features
Wraps RetrievalOrchestrator (Phase 1-4) and provides clean interface
"""

from typing import List, Dict, Any, Optional
import asyncio
from dataclasses import dataclass, field
from enum import Enum
import time

from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .embedding_service import get_embedding_service
from ..core.exceptions import RetrievalError, ServiceNotInitializedError
from ..utils.logging import get_logger

logger = get_logger(__name__)

# ═════════════════════════════════════════════════════════════════════════
# RETRIEVAL ORCHESTRATOR IMPORT (Module level for visibility in methods)
# ═════════════════════════════════════════════════════════════════════════

# Try to import RetrievalOrchestrator types (may fail if not available)
try:
    from .retrieval_orchestrator import (
        RetrievalOrchestrator,
        RetrievalStrategy as ORStrategy,
        RetrievalResult as ORResult,
    )

    RETRIEVAL_ORCHESTRATOR_AVAILABLE = True
except ImportError:
    RETRIEVAL_ORCHESTRATOR_AVAILABLE = False

    # Create stub enums for compatibility (at module level!)
    class ORStrategy(str, Enum):
        LEGACY = "legacy"
        PARALLEL_V1 = "parallel_v1"
        REWRITE_V1 = "rewrite_v1"
        RAG_FUSION = "rag_fusion"
        ADAPTIVE = "adaptive"

    @dataclass
    class ORResult:
        results: list
        metrics: Any
        success: bool
        error: Optional[str] = None

    @dataclass
    class RetrievalOrchestrator:
        """Stub orchestrator if not available"""

        DEFAULT_COLLECTIONS: list[str] = []
        MAX_CONCURRENT_QUERIES: int = 3

        def __init__(
            self,
            chromadb_client,
            embedding_function,
            default_timeout=5.0,
            query_rewriter=None,
            query_expander=None,
        ):
            self.client = chromadb_client
            self.embed_fn = embedding_function
            self._query_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_QUERIES)

        async def search(
            self,
            query,
            k=10,
            strategy=ORStrategy.PARALLEL_V1,
            where_filter=None,
            collections=None,
            history=None,
        ):
            return ORResult(
                results=[], metrics={}, success=False, error="Orchestrator not available"
            )


class RetrievalStrategy(str, Enum):
    """Available retrieval strategies"""

    LEGACY = "legacy"
    PARALLEL_V1 = "parallel_v1"
    REWRITE_V1 = "rewrite_v1"
    RAG_FUSION = "rag_fusion"
    ADAPTIVE = "adaptive"


@dataclass
class RetrievalMetrics:
    """Metrics for a single retrieval operation"""

    total_latency_ms: float = 0.0
    dense_latency_ms: float = 0.0
    bm25_latency_ms: float = 0.0

    dense_result_count: int = 0
    bm25_result_count: int = 0

    doc_overlap_count: int = 0
    unique_docs_total: int = 0

    top_score: float = 0.0
    mean_score: float = 0.0
    score_std: float = 0.0
    score_entropy: float = 0.0

    dense_timeout: bool = False
    bm25_timeout: bool = False

    strategy: str = "parallel_v1"

    rewrite_used: bool = False
    rewrite_latency_ms: float = 0.0
    original_query: str = ""
    rewritten_query: str = ""
    delta_topk_overlap: float = 0.0

    fusion_used: bool = False
    num_queries: int = 1
    query_variants: List[str] = field(default_factory=list)
    per_query_result_counts: List[int] = field(default_factory=list)
    unique_docs_before_fusion: int = 0
    unique_docs_after_fusion: int = 0
    overlap_ratio: float = 0.0
    fusion_gain: float = 0.0
    rrf_latency_ms: float = 0.0
    expansion_latency_ms: float = 0.0

    adaptive_used: bool = False
    confidence_signals: Optional[Dict] = None
    escalation_path: List[str] = field(default_factory=list)
    final_step: str = ""
    fallback_triggered: bool = False
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "latency": {
                "total_ms": round(self.total_latency_ms, 2),
                "dense_ms": round(self.dense_latency_ms, 2),
                "bm25_ms": round(self.bm25_latency_ms, 2),
            },
            "results": {
                "dense_count": self.dense_result_count,
                "bm25_count": self.bm25_result_count,
                "overlap": self.doc_overlap_count,
                "unique_total": self.unique_docs_total,
            },
            "scores": {
                "top": round(self.top_score, 4),
                "mean": round(self.mean_score, 4),
                "std": round(self.score_std, 4),
                "entropy": round(self.score_entropy, 4),
            },
            "timeouts": {
                "dense": self.dense_timeout,
                "bm25": self.bm25_timeout,
            },
            "strategy": self.strategy,
            "rewrite": {
                "used": self.rewrite_used,
                "latency_ms": round(self.rewrite_latency_ms, 2),
                "original_query": self.original_query,
                "rewritten_query": self.rewritten_query,
                "delta_topk_overlap": round(self.delta_topk_overlap, 4),
            },
            "fusion": {
                "used": self.fusion_used,
                "num_queries": self.num_queries,
                "query_variants": self.query_variants,
                "per_query_result_counts": self.per_query_result_counts,
                "unique_docs_before": self.unique_docs_before_fusion,
                "unique_docs_after": self.unique_docs_after_fusion,
                "overlap_ratio": round(self.overlap_ratio, 4),
                "fusion_gain": round(self.fusion_gain, 4),
                "rrf_latency_ms": round(self.rrf_latency_ms, 2),
                "expansion_latency_ms": round(self.expansion_latency_ms, 2),
            },
            "adaptive": {
                "used": self.adaptive_used,
                "signals": self.confidence_signals,
                "escalation_path": self.escalation_path,
                "final_step": self.final_step,
                "fallback_triggered": self.fallback_triggered,
                "reason_codes": self.reason_codes,
            },
        }


@dataclass
class SearchResult:
    """Individual search result with metadata"""

    id: str
    title: str
    snippet: str
    score: float
    source: str
    doc_type: Optional[str] = None
    date: Optional[str] = None
    retriever: str = "unknown"


@dataclass
class RetrievalResult:
    """Complete result from retrieval operation"""

    results: List[SearchResult]
    metrics: RetrievalMetrics
    success: bool = True
    error: Optional[str] = None


class RetrievalService(BaseService):
    """
    Retrieval Service - ChromaDB wrapper with advanced features.

    Wraps RetrievalOrchestrator (Phase 1-4) and provides:
    - Clean interface for ChromaDB operations
    - Parallel search with timeout handling
    - Query rewriting support
    - RAG-Fusion multi-query retrieval
    - Adaptive retrieval with confidence-based escalation
    - Graceful degradation on errors
    - Instrumentation/metrics collection
    """

    # Reference to module-level availability flag (for backward compatibility)
    RETRIEVAL_ORCHESTRATOR_AVAILABLE = RETRIEVAL_ORCHESTRATOR_AVAILABLE
    # References to module-level types (for backward compatibility)
    ORStrategy = ORStrategy
    ORResult = ORResult
    RetrievalOrchestrator = RetrievalOrchestrator

    def __init__(self, config: ConfigService):
        super().__init__(config)
        self._chromadb_client = None
        self._embedding_service = None
        self._orchestrator = None
        self.logger.info("Retrieval Service initialized")

    async def initialize(self) -> None:
        """Initialize ChromaDB connection and embedding service"""
        # Import chromadb here
        import chromadb
        import chromadb.config

        # Connect to ChromaDB
        try:
            chroma_path = self.config.chromadb_path
            logger.info(f"Connecting to ChromaDB at: {chroma_path}")

            settings = chromadb.config.Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )

            self._chromadb_client = chromadb.PersistentClient(
                path=chroma_path,
                settings=settings,
            )

            logger.info(
                f"ChromaDB connected (collections: {len(self._chromadb_client.list_collections())})"
            )

        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB: {e}")
            raise RetrievalError(f"ChromaDB connection failed: {str(e)}") from e

        # Initialize embedding service
        self._embedding_service = get_embedding_service(self.config)

        # Initialize RetrievalOrchestrator if available
        if self.RETRIEVAL_ORCHESTRATOR_AVAILABLE:
            try:
                self._orchestrator = self.RetrievalOrchestrator(
                    chromadb_client=self._chromadb_client,
                    embedding_function=self._embedding_service.embed,
                    default_timeout=self.config.search_timeout,
                    query_rewriter=None,  # Will be added separately
                    query_expander=None,  # Will be added separately
                )
                logger.info("RetrievalOrchestrator initialized")
            except Exception as e:
                logger.error(f"Failed to initialize RetrievalOrchestrator: {e}")
                self._orchestrator = None

        self._mark_initialized()

    async def health_check(self) -> bool:
        """Check if retrieval service is healthy"""
        try:
            await self.ensure_initialized()

            # Check ChromaDB
            collections = self._chromadb_client.list_collections()
            is_healthy = collections is not None

            logger.info(f"Retrieval Service health check: {'OK' if is_healthy else 'FAILED'}")
            return is_healthy

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self) -> None:
        """Cleanup ChromaDB connection"""
        if self._chromadb_client:
            logger.info("Closing ChromaDB connection")
            self._chromadb_client = None

        self._mark_uninitialized()

    async def ensure_initialized(self) -> None:
        """Ensure service is initialized"""
        super().ensure_initialized()

        if self._chromadb_client is None:
            raise ServiceNotInitializedError(
                "ChromaDB client not initialized. Call initialize() first."
            )

    async def search(
        self,
        query: str,
        k: int = 10,
        strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        where_filter: Optional[Dict] = None,
        collections: Optional[List[str]] = None,
        history: Optional[List[str]] = None,
    ) -> RetrievalResult:
        """
        Execute search with specified strategy.

        Args:
            query: Search query
            k: Number of results to return
            strategy: Which retrieval strategy to use
            where_filter: Optional ChromaDB where filter
            collections: Collections to search (default: all)
            history: Conversation history for query rewriting

        Returns:
            RetrievalResult with results and metrics

        Raises:
            RetrievalError: If search fails
        """
        await self.ensure_initialized()

        start_time = time.perf_counter()

        try:
            # Use provided collections or default
            collections_to_search = collections or self.config.default_collections

            # Map our RetrievalStrategy to orchestrator's strategy
            if self.RETRIEVAL_ORCHESTRATOR_AVAILABLE and self._orchestrator:
                strategy_map = {
                    RetrievalStrategy.LEGACY: ORStrategy.LEGACY,
                    RetrievalStrategy.PARALLEL_V1: ORStrategy.PARALLEL_V1,
                    RetrievalStrategy.REWRITE_V1: ORStrategy.REWRITE_V1,
                    RetrievalStrategy.RAG_FUSION: ORStrategy.RAG_FUSION,
                    RetrievalStrategy.ADAPTIVE: ORStrategy.ADAPTIVE,
                }
                orch_strategy = strategy_map.get(strategy, ORStrategy.PARALLEL_V1)

                # Execute search via orchestrator
                or_result = await self._orchestrator.search(
                    query=query,
                    k=k,
                    strategy=orch_strategy,
                    where_filter=where_filter,
                    collections=collections_to_search,
                    history=history,
                )

                # Convert orchestrator results to our format
                search_results = [
                    SearchResult(
                        id=r.id,
                        title=r.title,
                        snippet=r.snippet,
                        score=r.score,
                        source=r.source,
                        doc_type=r.doc_type,
                        date=r.date,
                        retriever=r.retriever,
                    )
                    for r in or_result.results[:k]
                ]

                # Convert metrics
                metrics_dict = (
                    or_result.metrics.to_dict() if hasattr(or_result.metrics, "to_dict") else {}
                )
                metrics = RetrievalMetrics(
                    total_latency_ms=metrics_dict.get("latency", {}).get("total_ms", 0.0),
                    dense_latency_ms=metrics_dict.get("latency", {}).get("dense_ms", 0.0),
                    bm25_latency_ms=metrics_dict.get("latency", {}).get("bm25_ms", 0.0),
                    dense_result_count=metrics_dict.get("results", {}).get("dense_count", 0),
                    bm25_result_count=metrics_dict.get("results", {}).get("bm25_count", 0),
                    doc_overlap_count=metrics_dict.get("results", {}).get("overlap", 0),
                    unique_docs_total=metrics_dict.get("results", {}).get("unique_total", 0),
                    top_score=metrics_dict.get("scores", {}).get("top", 0.0),
                    mean_score=metrics_dict.get("scores", {}).get("mean", 0.0),
                    score_std=metrics_dict.get("scores", {}).get("std", 0.0),
                    score_entropy=metrics_dict.get("scores", {}).get("entropy", 0.0),
                    dense_timeout=metrics_dict.get("timeouts", {}).get("dense", False),
                    bm25_timeout=metrics_dict.get("timeouts", {}).get("bm25", False),
                    strategy=metrics_dict.get("strategy", strategy.value),
                    rewrite_used=metrics_dict.get("rewrite", {}).get("used", False),
                    rewrite_latency_ms=metrics_dict.get("rewrite", {}).get("latency_ms", 0.0),
                    original_query=metrics_dict.get("rewrite", {}).get("original_query", ""),
                    rewritten_query=metrics_dict.get("rewrite", {}).get("rewritten_query", ""),
                    delta_topk_overlap=metrics_dict.get("rewrite", {}).get(
                        "delta_topk_overlap", 0.0
                    ),
                    fusion_used=metrics_dict.get("fusion", {}).get("used", False),
                    num_queries=metrics_dict.get("fusion", {}).get("num_queries", 1),
                    query_variants=metrics_dict.get("fusion", {}).get("query_variants", []),
                    per_query_result_counts=metrics_dict.get("fusion", {}).get(
                        "per_query_result_counts", []
                    ),
                    unique_docs_before_fusion=metrics_dict.get("fusion", {}).get(
                        "unique_docs_before", 0
                    ),
                    unique_docs_after_fusion=metrics_dict.get("fusion", {}).get(
                        "unique_docs_after", 0
                    ),
                    overlap_ratio=metrics_dict.get("fusion", {}).get("overlap_ratio", 0.0),
                    fusion_gain=metrics_dict.get("fusion", {}).get("fusion_gain", 0.0),
                    rrf_latency_ms=metrics_dict.get("fusion", {}).get("rrf_latency_ms", 0.0),
                    expansion_latency_ms=metrics_dict.get("fusion", {}).get(
                        "expansion_latency_ms", 0.0
                    ),
                    adaptive_used=metrics_dict.get("adaptive", {}).get("used", False),
                    confidence_signals=metrics_dict.get("adaptive", {}).get("signals"),
                    escalation_path=metrics_dict.get("adaptive", {}).get("escalation_path", []),
                    final_step=metrics_dict.get("adaptive", {}).get("final_step", ""),
                    fallback_triggered=metrics_dict.get("adaptive", {}).get(
                        "fallback_triggered", False
                    ),
                    reason_codes=metrics_dict.get("adaptive", {}).get("reason_codes", []),
                )

                logger.info(
                    f"Search complete: {len(search_results)} results in "
                    f"{metrics.total_latency_ms:.1f}ms (strategy: {strategy.value})"
                )

                return RetrievalResult(
                    results=search_results,
                    metrics=metrics,
                    success=or_result.success,
                    error=or_result.error,
                )

            else:
                # Fallback: simple ChromaDB query if orchestrator not available
                logger.warning("RetrievalOrchestrator not available, using fallback search")
                return await self._fallback_search(query, k, where_filter, collections_to_search)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise RetrievalError(f"Search failed: {str(e)}") from e

    async def _fallback_search(
        self,
        query: str,
        k: int,
        where_filter: Optional[Dict],
        collections: List[str],
    ) -> RetrievalResult:
        """
        Fallback search using simple ChromaDB query.

        Used when RetrievalOrchestrator is not available.
        """
        start_time = time.perf_counter()

        try:
            # Generate embedding
            query_embedding = self._embedding_service.embed_single(query)

            all_results = []

            # Search each collection
            for collection_name in collections:
                try:
                    collection = self._chromadb_client.get_collection(name=collection_name)

                    query_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=k,
                        where=where_filter,
                        include=["metadatas", "documents", "distances"],
                    )

                    if query_results and query_results.get("ids") and len(query_results["ids"]) > 0:
                        for i in range(len(query_results["ids"][0])):
                            doc_id = query_results["ids"][0][i]
                            metadata = query_results.get("metadatas", [{}])[0][i]
                            document = query_results.get("documents", [{}])[0][i]
                            distance = query_results.get("distances", [{}])[0][i]

                            score = 1.0 / (1.0 + distance)
                            snippet = document[:200] + "..." if len(document) > 200 else document

                            all_results.append(
                                SearchResult(
                                    id=doc_id,
                                    title=metadata.get("title", "Untitled"),
                                    snippet=snippet,
                                    score=round(score, 4),
                                    source=collection_name,
                                    doc_type=metadata.get("doc_type"),
                                    date=metadata.get("date"),
                                    retriever="dense",
                                )
                            )

                except Exception as e:
                    logger.warning(f"Error searching {collection_name}: {e}")
                    continue

            # Sort by score
            all_results.sort(key=lambda x: -x.score)
            results = all_results[:k]

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Create metrics
            metrics = RetrievalMetrics(
                total_latency_ms=latency_ms,
                strategy="legacy",
                unique_docs_total=len(results),
            )

            logger.info(f"Fallback search complete: {len(results)} results in {latency_ms:.1f}ms")

            return RetrievalResult(
                results=results,
                metrics=metrics,
                success=True,
            )

        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            raise RetrievalError(f"Fallback search failed: {str(e)}") from e

    async def list_collections(self) -> List[Dict[str, Any]]:
        """List all ChromaDB collections"""
        await self.ensure_initialized()

        try:
            collections = self._chromadb_client.list_collections()

            result = []
            for collection in collections:
                try:
                    count = collection.count()

                    # Get sample to infer metadata schema
                    sample = collection.get(limit=1, include=["metadatas"])
                    metadata_fields = []

                    if sample and sample.get("metadatas"):
                        # Collect unique metadata field names
                        all_fields = set()
                        for metadata in sample["metadatas"]:
                            all_fields.update(metadata.keys())
                        metadata_fields = sorted(list(all_fields))

                    result.append(
                        {
                            "name": collection.name,
                            "document_count": count,
                            "metadata_fields": metadata_fields,
                        }
                    )

                except Exception as e:
                    logger.warning(f"Error getting info for {collection.name}: {e}")
                    continue

            return result

        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            raise RetrievalError(f"Failed to list collections: {str(e)}") from e


# Dependency injection function for FastAPI
from functools import lru_cache


@lru_cache()
def get_retrieval_service(config: Optional[ConfigService] = None) -> RetrievalService:
    """Get singleton RetrievalService instance"""
    if config is None:
        config = get_config_service()

    return RetrievalService(config)
