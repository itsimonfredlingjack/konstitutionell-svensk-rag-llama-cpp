"""
Retrieval Service - ChromaDB Wrapper with Advanced Features
Wraps RetrievalOrchestrator (Phase 1-4) and provides clean interface
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

from ..core.exceptions import RetrievalError, ServiceNotInitializedError
from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .embedding_service import get_embedding_service

logger = get_logger(__name__)

# RAG Similarity Threshold - Direct env var (no config dependency)
SCORE_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.35"))

# ═════════════════════════════════════════════════════════════════════════
# RETRIEVAL ORCHESTRATOR IMPORT (Module level for visibility in methods)
# ═════════════════════════════════════════════════════════════════════════

# Try to import RetrievalOrchestrator types (may fail if not available)
try:
    from .retrieval_orchestrator import (
        RetrievalOrchestrator,
        RetrievalResult as ORResult,
        RetrievalStrategy as ORStrategy,
    )
    from .query_rewriter import QueryRewriter
    from .bm25_service import get_bm25_service

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

    intent: Optional[str] = None  # EPR: Query intent
    routing_used: Optional[Dict] = None  # EPR: Routing config used

    @dataclass
    class RetrievalOrchestrator:
        """Stub orchestrator if not available"""

        DEFAULT_COLLECTIONS: list[str] = field(default_factory=list)
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

        async def search_with_routing(
            self,
            query,
            k=10,
            where_filter=None,
            history=None,
        ):
            return ORResult(results=[], metrics={}, success=False, error="EPR not available (stub)")


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
    tier: Optional[str] = None  # EPR: Source tier (A/B/C)


@dataclass
class RetrievalResult:
    """Complete result from retrieval operation"""

    results: List[SearchResult]
    metrics: RetrievalMetrics
    success: bool = True
    error: Optional[str] = None
    intent: Optional[str] = None  # EPR: Query intent
    routing_used: Optional[Dict] = None  # EPR: Routing config used


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

        # CRITICAL: Verify query embedding dimension matches collection expectations
        try:
            # Test embedding dimension
            test_query = "ping"
            test_embedding = self._embedding_service.embed_single(test_query)
            actual_dim = len(test_embedding)
            expected_dim = self.config.expected_embedding_dim

            if actual_dim != expected_dim:
                raise RuntimeError(
                    f"FATAL: Query embedder dimension mismatch! "
                    f"Expected {expected_dim} (BGE-M3), got {actual_dim}. "
                    f"Query embedder must match collection embedding dimension. "
                    f"Fix: Update embedding_model in config to match migrated collections."
                )

            logger.info(f"✅ Query embedder verified: {actual_dim}-dim (matches collections)")

            # Verify collections exist and have correct dimension
            if self.config.expected_embedding_dim == 1024:
                existing = {c.name for c in self._chromadb_client.list_collections()}
                expected = set(self.config.effective_default_collections)
                missing = sorted(list(expected - existing))
                if missing:
                    logger.warning(
                        "Embedding dimension is 1024 (BGE-M3) but expected Chroma collections are missing. "
                        "Search will return empty results until re-indexing is completed. "
                        f"Missing collections: {missing}"
                    )
                else:
                    # Verify collection dimensions by querying one
                    for coll_name in self.config.effective_default_collections:
                        try:
                            collection = self._chromadb_client.get_collection(name=coll_name)
                            # Try a test query to verify dimension compatibility
                            _ = collection.query(
                                query_embeddings=[test_embedding],
                                n_results=1,
                            )
                            logger.info(
                                f"✅ Collection {coll_name} verified: accepts {actual_dim}-dim queries"
                            )
                        except Exception as e:
                            error_msg = str(e).lower()
                            if "dimension" in error_msg or "expecting embedding" in error_msg:
                                raise RuntimeError(
                                    f"FATAL: Collection {coll_name} dimension mismatch! "
                                    f"Collection expects different dimension than query embedder ({actual_dim}). "
                                    f"Error: {e}"
                                )
                            else:
                                logger.warning(f"Could not verify collection {coll_name}: {e}")

        except RuntimeError:
            # Re-raise dimension mismatch errors
            raise
        except Exception as e:
            logger.warning(f"Unable to validate embedding dimensions: {e}")

        # Initialize RetrievalOrchestrator if available
        if self.RETRIEVAL_ORCHESTRATOR_AVAILABLE:
            try:
                # Initialize QueryRewriter för förkortningsexpansion
                query_rewriter = QueryRewriter()
                logger.info("QueryRewriter initialized (with abbreviation expansion)")

                # Initialize BM25 service for hybrid search
                bm25_service = get_bm25_service()
                if bm25_service.is_available():
                    logger.info(f"BM25 service available at {bm25_service.index_path}")
                else:
                    logger.warning("BM25 index not found - hybrid search disabled")
                    bm25_service = None

                self._orchestrator = self.RetrievalOrchestrator(
                    chromadb_client=self._chromadb_client,
                    embedding_function=self._embedding_service.embed,
                    default_timeout=self.config.search_timeout,
                    query_rewriter=query_rewriter,  # Aktiverar förkortningsexpansion
                    query_expander=None,  # Will be added separately
                    default_collections=self.config.effective_default_collections,
                    bm25_service=bm25_service,  # Hybrid search: BM25 sidecar
                    bm25_weight=self.config.rrf_bm25_weight,  # Favor exact legal terms
                    rrf_k=self.config.rrf_k,  # Lower k = top results dominate
                )
                logger.info(
                    f"RetrievalOrchestrator initialized (bm25_weight={self.config.rrf_bm25_weight}, "
                    f"rrf_k={self.config.rrf_k})"
                )
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
        await super().ensure_initialized()

        if self._chromadb_client is None:
            raise ServiceNotInitializedError(
                "ChromaDB client not initialized. Call initialize() first."
            )

    async def search(
        self,
        query: str,
        k: int = 10,
        strategy: RetrievalStrategy | str = RetrievalStrategy.PARALLEL_V1,
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

        try:
            # Phase 5: Intent-based collection routing
            collections_to_search = collections
            if collections_to_search is None:
                try:
                    from .intent_classifier import get_intent_classifier

                    intent_classifier = get_intent_classifier()
                    intent_result = intent_classifier.classify(query)

                    if intent_result.confidence >= 0.60:
                        collections_to_search = intent_result.suggested_collections
                        logger.info(
                            f"Intent routing: {intent_result.intent.value} "
                            f"(conf: {intent_result.confidence:.2f}) -> "
                            f"{collections_to_search[:2]}..."
                        )
                    else:
                        collections_to_search = self.config.effective_default_collections
                        logger.debug(
                            f"Intent routing: {intent_result.intent.value} "
                            f"(conf: {intent_result.confidence:.2f}) - using defaults"
                        )
                except Exception as e:
                    logger.warning(f"Intent classification failed: {e}")
                    collections_to_search = self.config.effective_default_collections

            # Fallback to defaults if still None
            if collections_to_search is None:
                collections_to_search = self.config.effective_default_collections

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

                # Convert metrics - optimized: cache nested dictionaries
                metrics_dict = (
                    or_result.metrics.to_dict() if hasattr(or_result.metrics, "to_dict") else {}
                )

                # Cache nested dictionaries to avoid repeated .get() calls
                latency_dict = metrics_dict.get("latency", {})
                results_dict = metrics_dict.get("results", {})
                scores_dict = metrics_dict.get("scores", {})
                timeouts_dict = metrics_dict.get("timeouts", {})
                rewrite_dict = metrics_dict.get("rewrite", {})
                fusion_dict = metrics_dict.get("fusion", {})
                adaptive_dict = metrics_dict.get("adaptive", {})

                metrics = RetrievalMetrics(
                    total_latency_ms=latency_dict.get("total_ms", 0.0),
                    dense_latency_ms=latency_dict.get("dense_ms", 0.0),
                    bm25_latency_ms=latency_dict.get("bm25_ms", 0.0),
                    dense_result_count=results_dict.get("dense_count", 0),
                    bm25_result_count=results_dict.get("bm25_count", 0),
                    doc_overlap_count=results_dict.get("overlap", 0),
                    unique_docs_total=results_dict.get("unique_total", 0),
                    top_score=scores_dict.get("top", 0.0),
                    mean_score=scores_dict.get("mean", 0.0),
                    score_std=scores_dict.get("std", 0.0),
                    score_entropy=scores_dict.get("entropy", 0.0),
                    dense_timeout=timeouts_dict.get("dense", False),
                    bm25_timeout=timeouts_dict.get("bm25", False),
                    strategy=metrics_dict.get(
                        "strategy", strategy if isinstance(strategy, str) else strategy.value
                    ),
                    rewrite_used=rewrite_dict.get("used", False),
                    rewrite_latency_ms=rewrite_dict.get("latency_ms", 0.0),
                    original_query=rewrite_dict.get("original_query", ""),
                    rewritten_query=rewrite_dict.get("rewritten_query", ""),
                    delta_topk_overlap=rewrite_dict.get("delta_topk_overlap", 0.0),
                    fusion_used=fusion_dict.get("used", False),
                    num_queries=fusion_dict.get("num_queries", 1),
                    query_variants=fusion_dict.get("query_variants", []),
                    per_query_result_counts=fusion_dict.get("per_query_result_counts", []),
                    unique_docs_before_fusion=fusion_dict.get("unique_docs_before", 0),
                    unique_docs_after_fusion=fusion_dict.get("unique_docs_after", 0),
                    overlap_ratio=fusion_dict.get("overlap_ratio", 0.0),
                    fusion_gain=fusion_dict.get("fusion_gain", 0.0),
                    rrf_latency_ms=fusion_dict.get("rrf_latency_ms", 0.0),
                    expansion_latency_ms=fusion_dict.get("expansion_latency_ms", 0.0),
                    adaptive_used=adaptive_dict.get("used", False),
                    confidence_signals=adaptive_dict.get("signals"),
                    escalation_path=adaptive_dict.get("escalation_path", []),
                    final_step=adaptive_dict.get("final_step", ""),
                    fallback_triggered=adaptive_dict.get("fallback_triggered", False),
                    reason_codes=adaptive_dict.get("reason_codes", []),
                )

                logger.info(
                    f"Search complete: {len(search_results)} results in "
                    f"{metrics.total_latency_ms:.1f}ms (strategy: {strategy if isinstance(strategy, str) else strategy.value})"
                )

                # Apply similarity threshold filtering (BEFORE trimming to k)
                qualified_results = [r for r in search_results if r.score >= SCORE_THRESHOLD]

                # Adaptive fallback: if all filtered out, return top 3 anyway but log warning
                if not qualified_results and search_results:
                    qualified_results = search_results[:3]
                    logger.warning(
                        f"All {len(search_results)} results below threshold {SCORE_THRESHOLD:.3f}. "
                        f"Adaptive fallback: returning top 3 results."
                    )

                # Trim to requested k
                search_results = qualified_results[:k]

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

            # OPTIMIZED: Parallel collection queries to fix N+1 problem
            # Use run_in_executor since ChromaDB queries are synchronous
            def query_single_collection(collection_name: str):
                """Query a single collection and return results (synchronous)."""
                try:
                    collection = self._chromadb_client.get_collection(name=collection_name)
                    query_results = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=k,
                        where=where_filter,
                        include=["metadatas", "documents", "distances"],
                    )

                    results = []
                    if query_results and query_results.get("ids") and len(query_results["ids"]) > 0:
                        # Cache repeated dictionary access
                        ids_list = query_results["ids"][0]
                        metadatas_list = query_results.get("metadatas", [{}])[0]
                        documents_list = query_results.get("documents", [{}])[0]
                        distances_list = query_results.get("distances", [{}])[0]

                        # Detect distance metric from collection metadata
                        space = (
                            collection.metadata.get("hnsw:space", "l2")
                            if collection.metadata
                            else "l2"
                        )

                        for i in range(len(ids_list)):
                            doc_id = ids_list[i]
                            metadata = metadatas_list[i] if i < len(metadatas_list) else {}
                            document = documents_list[i] if i < len(documents_list) else ""
                            distance = distances_list[i] if i < len(distances_list) else 1.0

                            if space == "cosine":
                                score = 1.0 - distance  # cosine distance -> similarity
                            elif space == "ip":
                                score = distance  # inner product already similarity-like
                            else:  # l2
                                score = 1.0 / (1.0 + distance)
                            snippet = document[:1500] + "..." if len(document) > 1500 else document

                            results.append(
                                SearchResult(
                                    id=doc_id,
                                    title=str(metadata.get("title", "Untitled")),
                                    snippet=snippet,
                                    score=round(score, 4),
                                    source=collection_name,
                                    doc_type=str(metadata.get("doc_type") or ""),
                                    date=str(metadata.get("date") or ""),
                                    retriever="dense",
                                )
                            )
                    return results
                except Exception as e:
                    logger.warning(f"Error searching {collection_name}: {e}")
                    return []

            # Execute all collection queries in parallel using executor
            import asyncio

            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(None, query_single_collection, name) for name in collections
            ]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)

            # Flatten results
            for results in results_list:
                if isinstance(results, Exception):
                    continue
                all_results.extend(results)

            # Sort by score
            all_results.sort(key=lambda x: -x.score)

            # Apply similarity threshold filtering (BEFORE trimming to k)
            qualified_results = [r for r in all_results if r.score >= SCORE_THRESHOLD]

            # Adaptive fallback: if all filtered out, return top 3 anyway but log warning
            if not qualified_results and all_results:
                qualified_results = all_results[:3]
                logger.warning(
                    f"All {len(all_results)} results below threshold {SCORE_THRESHOLD:.3f}. "
                    f"Adaptive fallback: returning top 3 results."
                )

            # Trim to requested k
            results = qualified_results[:k]

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

    async def search_with_epr(
        self,
        query: str,
        k: int = 10,
        where_filter: Optional[Dict] = None,
        history: Optional[List[str]] = None,
    ) -> RetrievalResult:
        """
        Execute search with Evidence Policy Routing (EPR).

        This method wraps the orchestrator's search_with_routing() method
        for two-pass retrieval with intent-based collection routing.

        Args:
            query: Search query
            k: Number of results to return
            where_filter: Optional ChromaDB where filter
            history: Conversation history for intent classification context

        Returns:
            RetrievalResult with results sorted by tier, intent, and routing metadata
        """
        await self.ensure_initialized()

        if not self._orchestrator:
            raise RetrievalError("Orchestrator not initialized")

        try:
            # Call orchestrator's two-pass routing
            orchestrator_result = await self._orchestrator.search_with_routing(
                query=query,
                k=k,
                where_filter=where_filter,
                history=history,
            )

            # Convert orchestrator results to RetrievalService format
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
                    tier=r.tier,  # EPR: Include tier
                )
                for r in orchestrator_result.results
            ]

            # Convert metrics
            or_metrics = orchestrator_result.metrics
            metrics_dict = or_metrics.to_dict() if hasattr(or_metrics, "to_dict") else {}

            # Cache nested dictionaries
            latency_dict = metrics_dict.get("latency", {})
            results_dict = metrics_dict.get("results", {})
            scores_dict = metrics_dict.get("scores", {})
            timeouts_dict = metrics_dict.get("timeouts", {})

            metrics = RetrievalMetrics(
                strategy="epr_two_pass",
                total_latency_ms=latency_dict.get("total_ms", or_metrics.total_latency_ms),
                dense_latency_ms=latency_dict.get("dense_ms", or_metrics.dense_latency_ms),
                bm25_latency_ms=latency_dict.get("bm25_ms", or_metrics.bm25_latency_ms),
                dense_result_count=results_dict.get("dense_count", or_metrics.dense_result_count),
                bm25_result_count=results_dict.get("bm25_count", or_metrics.bm25_result_count),
                doc_overlap_count=results_dict.get("overlap", or_metrics.doc_overlap_count),
                unique_docs_total=results_dict.get("unique_total", or_metrics.unique_docs_total),
                top_score=scores_dict.get("top", or_metrics.top_score),
                mean_score=scores_dict.get("mean", or_metrics.mean_score),
                score_std=scores_dict.get("std", or_metrics.score_std),
                score_entropy=scores_dict.get("entropy", or_metrics.score_entropy),
                dense_timeout=timeouts_dict.get("dense", or_metrics.dense_timeout),
                bm25_timeout=timeouts_dict.get("bm25", or_metrics.bm25_timeout),
            )

            logger.info(
                f"EPR search complete: {len(search_results)} results in "
                f"{metrics.total_latency_ms:.1f}ms (intent: {orchestrator_result.intent})"
            )

            return RetrievalResult(
                results=search_results,
                metrics=metrics,
                success=orchestrator_result.success,
                error=orchestrator_result.error,
                intent=orchestrator_result.intent,
                routing_used=orchestrator_result.routing_used,
            )

        except Exception as e:
            logger.error(f"EPR search failed: {e}")
            raise RetrievalError(f"EPR search failed: {str(e)}") from e


# Dependency injection function for FastAPI


@lru_cache()
def get_retrieval_service(config: Optional[ConfigService] = None) -> RetrievalService:
    """Get singleton RetrievalService instance"""
    if config is None:
        config = get_config_service()

    return RetrievalService(config)
