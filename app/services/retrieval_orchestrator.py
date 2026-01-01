"""
Retrieval Orchestrator - Phase 1, 2, 3 & 4: Complete Smarter Retrieval Stack
=============================================================================

Centralized retrieval logic for Constitutional AI.
Supports parallel search, graceful degradation, query rewriting, and instrumentation.

Phase 1: Parallel collection search with timeout handling ✓
Phase 2: Query rewriting with decontextualization ✓
Phase 3: RAG-Fusion multi-query with RRF merge ✓
Phase 4: Adaptive retrieval with confidence-based escalation ✓

Adaptive Retrieval (Phase 4):
- Computes confidence signals (top_score, margin, must_include_hit_rate, etc.)
- Escalates in cheap steps: A→B→C→D
- Step A: rag_fusion 2 queries
- Step B: increase k_pre_rerank, search more collections
- Step C: rag_fusion 3 queries
- Step D: fallback (ask for clarification)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum

# Phase 3: RAG-Fusion imports
from app.services.rag_fusion import (
    QueryExpander,
    ExpandedQueries,
    FusionMetrics,
    reciprocal_rank_fusion,
    calculate_fusion_metrics,
    validate_no_hallucinated_entities,
)

# Phase 4: Confidence signals for adaptive retrieval
from app.services.confidence_signals import (
    ConfidenceSignals,
    ConfidenceCalculator,
    EscalationPolicy,
    AdaptiveResult,
)

logger = logging.getLogger("constitutional.retrieval")


# ═══════════════════════════════════════════════════════════════════════════
# METRICS & INSTRUMENTATION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RetrievalMetrics:
    """Metrics for a single retrieval operation - designed for Phase 4 confidence."""
    total_latency_ms: float = 0.0
    dense_latency_ms: float = 0.0
    bm25_latency_ms: float = 0.0

    # Per-retriever results
    dense_result_count: int = 0
    bm25_result_count: int = 0

    # Score distribution (for Phase 4 confidence)
    top_score: float = 0.0
    mean_score: float = 0.0
    score_std: float = 0.0
    score_entropy: float = 0.0

    # Overlap metrics
    doc_overlap_count: int = 0  # Docs found by both retrievers
    unique_docs_total: int = 0

    # Timeout tracking
    dense_timeout: bool = False
    bm25_timeout: bool = False

    # Strategy used
    strategy: str = "parallel_v1"

    # Phase 2: Query rewriting metrics
    rewrite_used: bool = False
    rewrite_latency_ms: float = 0.0
    original_query: str = ""
    rewritten_query: str = ""
    delta_topk_overlap: float = 0.0  # How different are rewritten results?

    # Phase 3: RAG-Fusion metrics
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

    # Phase 4: Adaptive retrieval metrics
    adaptive_used: bool = False
    confidence_signals: Optional[Dict] = None
    escalation_path: List[str] = field(default_factory=list)
    final_step: str = ""
    fallback_triggered: bool = False
    reason_codes: List[str] = field(default_factory=list)  # Decision trace for debugging

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for logging/API response."""
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
                "reason_codes": self.reason_codes,  # Decision trace
            },
        }


@dataclass
class SearchResult:
    """Individual search result with score and metadata."""
    id: str
    title: str
    snippet: str
    score: float
    source: str
    doc_type: Optional[str] = None
    date: Optional[str] = None
    retriever: str = "unknown"  # 'dense', 'bm25', or 'both'


@dataclass
class RetrievalResult:
    """Complete result from retrieval orchestrator."""
    results: List[SearchResult]
    metrics: RetrievalMetrics
    success: bool = True
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# RETRIEVAL STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════

class RetrievalStrategy(Enum):
    """Available retrieval strategies."""
    LEGACY = "legacy"  # Original sequential search
    PARALLEL_V1 = "parallel_v1"  # Phase 1: Parallel dense + collections
    REWRITE_V1 = "rewrite_v1"  # Phase 2: Query rewriting + parallel search
    RAG_FUSION = "rag_fusion"  # Phase 3
    ADAPTIVE = "adaptive"  # Phase 4


# ═══════════════════════════════════════════════════════════════════════════
# PARALLEL COLLECTION SEARCH (PHASE 1)
# ═══════════════════════════════════════════════════════════════════════════

async def search_single_collection(
    collection,
    query_embedding: List[float],
    n_results: int,
    where_filter: Optional[Dict] = None,
    timeout_seconds: float = 5.0,
) -> Tuple[List[Dict], float, bool]:
    """
    Search a single ChromaDB collection with timeout.

    Returns:
        Tuple of (results, latency_ms, timed_out)
    """
    start = time.perf_counter()
    timed_out = False
    results = []

    try:
        # Wrap synchronous ChromaDB call in executor for true async
        loop = asyncio.get_event_loop()

        def _query():
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter if where_filter else None,
                include=["metadatas", "documents", "distances"]
            )

        # Run with timeout
        query_results = await asyncio.wait_for(
            loop.run_in_executor(None, _query),
            timeout=timeout_seconds
        )

        # Parse results
        if query_results and query_results.get("ids") and len(query_results["ids"]) > 0:
            for i in range(len(query_results["ids"][0])):
                doc_id = query_results["ids"][0][i]
                metadata = query_results["metadatas"][0][i] if query_results.get("metadatas") else {}
                document = query_results["documents"][0][i] if query_results.get("documents") else ""
                distance = query_results["distances"][0][i] if query_results.get("distances") else 1.0

                # Convert distance to score (0-1, higher is better)
                score = 1.0 / (1.0 + distance)

                results.append({
                    "id": doc_id,
                    "title": metadata.get("title", "Untitled"),
                    "snippet": document[:200] + "..." if len(document) > 200 else document,
                    "score": score,
                    "source": metadata.get("source", collection.name),
                    "doc_type": metadata.get("doc_type"),
                    "date": metadata.get("date"),
                    "collection": collection.name,
                })

    except asyncio.TimeoutError:
        timed_out = True
        logger.warning(f"Collection {collection.name} timed out after {timeout_seconds}s")
    except Exception as e:
        logger.error(f"Error searching {collection.name}: {e}")

    latency_ms = (time.perf_counter() - start) * 1000
    return results, latency_ms, timed_out


async def parallel_collection_search(
    client,
    query_embedding: List[float],
    collection_names: List[str],
    n_results_per_collection: int = 10,
    where_filter: Optional[Dict] = None,
    timeout_seconds: float = 5.0,
) -> Tuple[List[Dict], RetrievalMetrics]:
    """
    Search multiple collections in parallel with graceful degradation.

    If any collection times out, we still return results from successful ones.
    """
    start_total = time.perf_counter()
    metrics = RetrievalMetrics(strategy="parallel_v1")

    # Get all collections
    collections = []
    for name in collection_names:
        try:
            collections.append((name, client.get_collection(name=name)))
        except Exception as e:
            logger.warning(f"Collection {name} not found: {e}")

    if not collections:
        return [], metrics

    # Create tasks for parallel execution
    tasks = [
        search_single_collection(
            collection=coll,
            query_embedding=query_embedding,
            n_results=n_results_per_collection,
            where_filter=where_filter,
            timeout_seconds=timeout_seconds,
        )
        for name, coll in collections
    ]

    # Execute all in parallel
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge results
    all_results = []
    collection_latencies = []

    for i, result in enumerate(results_list):
        coll_name = collections[i][0]

        if isinstance(result, Exception):
            logger.error(f"Collection {coll_name} failed: {result}")
            continue

        results, latency_ms, timed_out = result
        collection_latencies.append(latency_ms)

        if timed_out:
            if "dense" in coll_name.lower() or "sfs" in coll_name.lower():
                metrics.dense_timeout = True
            else:
                metrics.bm25_timeout = True
        else:
            all_results.extend(results)

            # Track counts (simplified - assume first collection is "dense-like")
            if i == 0:
                metrics.dense_result_count = len(results)
                metrics.dense_latency_ms = latency_ms
            else:
                metrics.bm25_result_count += len(results)
                metrics.bm25_latency_ms = max(metrics.bm25_latency_ms, latency_ms)

    # Calculate total latency (should be ~max, not sum, due to parallelism)
    metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000

    # Deduplicate by doc ID, keeping highest score
    seen_ids = {}
    for r in all_results:
        doc_id = r["id"]
        if doc_id not in seen_ids or r["score"] > seen_ids[doc_id]["score"]:
            seen_ids[doc_id] = r

    unique_results = list(seen_ids.values())
    metrics.unique_docs_total = len(unique_results)

    # Calculate overlap (docs found in multiple collections - approximate)
    # This is a simplified calculation
    total_before_dedup = len(all_results)
    metrics.doc_overlap_count = total_before_dedup - len(unique_results)

    # Sort by score (RRF would go here in Phase 3)
    unique_results.sort(key=lambda x: x["score"], reverse=True)

    # Calculate score statistics for Phase 4
    if unique_results:
        scores = [r["score"] for r in unique_results]
        metrics.top_score = scores[0]
        metrics.mean_score = sum(scores) / len(scores)

        if len(scores) > 1:
            mean = metrics.mean_score
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            metrics.score_std = variance ** 0.5

            # Simplified entropy (normalized)
            # Higher entropy = more uniform distribution = less confident
            if metrics.top_score > 0:
                normalized_scores = [s / sum(scores) for s in scores]
                import math
                entropy = -sum(p * math.log(p + 1e-10) for p in normalized_scores if p > 0)
                max_entropy = math.log(len(scores))
                metrics.score_entropy = entropy / max_entropy if max_entropy > 0 else 0

    logger.info(
        f"Parallel search: {len(unique_results)} results in {metrics.total_latency_ms:.1f}ms "
        f"(dense: {metrics.dense_latency_ms:.1f}ms, bm25: {metrics.bm25_latency_ms:.1f}ms)"
    )

    return unique_results, metrics


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

class RetrievalOrchestrator:
    """
    Main orchestrator for retrieval strategies.

    Usage:
        orchestrator = RetrievalOrchestrator(chromadb_client, embed_fn)
        result = await orchestrator.search("GDPR personuppgifter", k=10)

        # With query rewriting (Phase 2):
        from app.services.query_rewriter import QueryRewriter
        rewriter = QueryRewriter()
        orchestrator = RetrievalOrchestrator(client, embed_fn, query_rewriter=rewriter)
        result = await orchestrator.search(
            "Vad säger den?",
            history=["Berätta om GDPR"],
            strategy=RetrievalStrategy.REWRITE_V1
        )
    """

    DEFAULT_COLLECTIONS = ["sfs_lagtext", "riksdag_documents_p1", "swedish_gov_docs"]

    # Concurrency control for multi-query (Phase 3)
    MAX_CONCURRENT_QUERIES = 3

    def __init__(
        self,
        chromadb_client,
        embedding_function,
        default_timeout: float = 5.0,
        query_rewriter=None,  # Phase 2: Optional QueryRewriter instance
        query_expander=None,  # Phase 3: Optional QueryExpander instance
    ):
        self.client = chromadb_client
        self.embed_fn = embedding_function
        self.default_timeout = default_timeout
        self.rewriter = query_rewriter
        self.expander = query_expander or QueryExpander(max_queries=3)
        self._query_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_QUERIES)

    async def search(
        self,
        query: str,
        k: int = 10,
        strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        where_filter: Optional[Dict] = None,
        collections: Optional[List[str]] = None,
        history: Optional[List[str]] = None,  # Phase 2: Conversation history
    ) -> RetrievalResult:
        """
        Execute search with specified strategy.

        Args:
            query: Search query
            k: Number of results to return
            strategy: Which retrieval strategy to use
            where_filter: Optional ChromaDB where filter
            collections: Collections to search (default: all)
            history: Conversation history for decontextualization (Phase 2)

        Returns:
            RetrievalResult with results and metrics
        """
        start = time.perf_counter()

        try:
            # Phase 2: Handle query rewriting if strategy is REWRITE_V1
            search_query = query
            rewrite_result = None

            if strategy == RetrievalStrategy.REWRITE_V1 and self.rewriter:
                rewrite_result = self.rewriter.rewrite(query, history)
                search_query = rewrite_result.standalone_query
                logger.info(
                    f"Query rewritten: '{query}' → '{search_query}' "
                    f"(latency: {rewrite_result.rewrite_latency_ms:.2f}ms)"
                )

            # Generate embedding for the (possibly rewritten) query
            query_embedding = self.embed_fn([search_query])[0]

            # Execute parallel search (for both PARALLEL_V1 and REWRITE_V1)
            if strategy in (RetrievalStrategy.PARALLEL_V1, RetrievalStrategy.REWRITE_V1):
                results, metrics = await parallel_collection_search(
                    client=self.client,
                    query_embedding=query_embedding,
                    collection_names=collections or self.DEFAULT_COLLECTIONS,
                    n_results_per_collection=k,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )

                # Update strategy in metrics
                metrics.strategy = strategy.value

                # Add rewrite metrics if used
                if rewrite_result:
                    metrics.rewrite_used = rewrite_result.rewrite_used
                    metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
                    metrics.original_query = query
                    metrics.rewritten_query = search_query

                # Convert to SearchResult objects
                search_results = [
                    SearchResult(
                        id=r["id"],
                        title=r["title"],
                        snippet=r["snippet"],
                        score=r["score"],
                        source=r["source"],
                        doc_type=r.get("doc_type"),
                        date=r.get("date"),
                        retriever="dense",
                    )
                    for r in results[:k]  # Limit to k
                ]

                # FIX: Override total_latency_ms to include embedding time + rewrite time
                metrics.total_latency_ms = (time.perf_counter() - start) * 1000

                return RetrievalResult(
                    results=search_results,
                    metrics=metrics,
                    success=True,
                )

            # Phase 3: RAG-Fusion
            elif strategy == RetrievalStrategy.RAG_FUSION:
                return await self._search_rag_fusion(
                    query=query,
                    k=k,
                    history=history,
                    collections=collections,
                    where_filter=where_filter,
                )

            # Phase 4: Adaptive Retrieval
            elif strategy == RetrievalStrategy.ADAPTIVE:
                return await self._search_adaptive(
                    query=query,
                    k=k,
                    history=history,
                    collections=collections,
                    where_filter=where_filter,
                )

            # Unknown strategy
            else:
                raise NotImplementedError(f"Strategy {strategy} not yet implemented")

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return RetrievalResult(
                results=[],
                metrics=RetrievalMetrics(
                    total_latency_ms=(time.perf_counter() - start) * 1000,
                    strategy=strategy.value,
                ),
                success=False,
                error=str(e),
            )

    async def _search_rag_fusion(
        self,
        query: str,
        k: int,
        history: Optional[List[str]],
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
    ) -> RetrievalResult:
        """
        Phase 3: RAG-Fusion multi-query retrieval with RRF merge.

        Flow:
        1. Rewrite query (Phase 2) if rewriter available
        2. Expand to multiple query variants (Q0, Q1, Q2)
        3. Batch embed all queries
        4. Search each embedding in parallel (with semaphore)
        5. Merge results with RRF (k=60)
        6. Return with fusion metrics
        """
        start_total = time.perf_counter()
        metrics = RetrievalMetrics(strategy="rag_fusion")

        # Step 1: Rewrite query if rewriter available
        search_query = query
        rewrite_result = None

        if self.rewriter:
            rewrite_result = self.rewriter.rewrite(query, history)
            search_query = rewrite_result.standalone_query
            metrics.rewrite_used = rewrite_result.rewrite_used
            metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
            metrics.original_query = query
            metrics.rewritten_query = search_query

        # Step 2: Expand to multiple query variants
        if rewrite_result:
            expanded = self.expander.expand(search_query, rewrite_result)
        else:
            # Create a minimal rewrite result for expansion
            from dataclasses import dataclass

            @dataclass
            class MinimalRewriteResult:
                standalone_query: str = ""
                lexical_query: str = ""
                detected_entities: list = None

                def __post_init__(self):
                    if self.detected_entities is None:
                        self.detected_entities = []

            minimal_result = MinimalRewriteResult(
                standalone_query=search_query,
                lexical_query="",
                detected_entities=[],
            )
            expanded = self.expander.expand(search_query, minimal_result)

        metrics.expansion_latency_ms = expanded.expansion_latency_ms
        metrics.num_queries = len(expanded.queries)
        metrics.query_variants = expanded.queries

        # Step 3: Batch embed all queries
        embed_start = time.perf_counter()
        query_embeddings = self.embed_fn(expanded.queries)
        embed_latency = (time.perf_counter() - embed_start) * 1000

        logger.info(
            f"Batch embedding: {len(expanded.queries)} queries in {embed_latency:.1f}ms"
        )

        # Step 4: Search each embedding in parallel (with semaphore)
        collection_names = collections or self.DEFAULT_COLLECTIONS

        async def search_single_embedding(embedding: List[float]) -> List[Dict]:
            """Search with semaphore to prevent self-DDoS."""
            async with self._query_semaphore:
                results, _ = await parallel_collection_search(
                    client=self.client,
                    query_embedding=embedding,
                    collection_names=collection_names,
                    n_results_per_collection=k,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )
                return results

        # Execute all searches in parallel
        search_start = time.perf_counter()
        tasks = [search_single_embedding(emb) for emb in query_embeddings]
        result_sets = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_result_sets = []
        for i, result in enumerate(result_sets):
            if isinstance(result, Exception):
                logger.error(f"Query {i} failed: {result}")
                valid_result_sets.append([])  # Empty result set
            else:
                valid_result_sets.append(result)

        metrics.per_query_result_counts = [len(rs) for rs in valid_result_sets]
        search_latency = (time.perf_counter() - search_start) * 1000

        # Step 5: Merge with RRF
        rrf_start = time.perf_counter()
        merged_results = reciprocal_rank_fusion(valid_result_sets, k=60.0)
        metrics.rrf_latency_ms = (time.perf_counter() - rrf_start) * 1000

        # Step 6: Calculate fusion metrics
        fusion_metrics = calculate_fusion_metrics(
            result_sets=valid_result_sets,
            merged_results=merged_results,
            expanded_queries=expanded,
        )

        metrics.fusion_used = True
        metrics.unique_docs_before_fusion = fusion_metrics.unique_docs_before_fusion
        metrics.unique_docs_after_fusion = fusion_metrics.unique_docs_after_fusion
        metrics.overlap_ratio = fusion_metrics.overlap_ratio
        metrics.fusion_gain = fusion_metrics.fusion_gain

        # Calculate total latency
        metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                id=r["id"],
                title=r.get("title", "Untitled"),
                snippet=r.get("snippet", ""),
                score=r.get("rrf_score", r.get("score", 0.0)),
                source=r.get("source", "unknown"),
                doc_type=r.get("doc_type"),
                date=r.get("date"),
                retriever="fusion",
            )
            for r in merged_results[:k]
        ]

        logger.info(
            f"RAG-Fusion complete: {len(search_results)} results in {metrics.total_latency_ms:.1f}ms "
            f"(queries: {metrics.num_queries}, gain: {metrics.fusion_gain:.1%})"
        )

        return RetrievalResult(
            results=search_results,
            metrics=metrics,
            success=True,
        )

    async def _search_adaptive(
        self,
        query: str,
        k: int,
        history: Optional[List[str]],
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
    ) -> RetrievalResult:
        """
        Phase 4: Adaptive retrieval with confidence-based escalation.

        Policy: Escalate in cheap, clear steps (Self-RAG inspired):
          Step A: rag_fusion with 2 queries → return if confidence OK
          Step B: increase k_pre_rerank, search all collections → return if OK
          Step C: rag_fusion with 3 queries → return if OK
          Step D: fallback (ask for clarification, or HyDE later)

        No additional LLM calls - confidence computed from retrieval signals:
          - top_score, margin (ranking certainty)
          - must_include_hit_rate (coverage)
          - overlap_ratio, fusion_gain (query agreement)
          - near_duplicate_ratio (diversity)
        """
        start_total = time.perf_counter()
        metrics = RetrievalMetrics(strategy="adaptive")
        metrics.adaptive_used = True

        # Initialize confidence calculator
        confidence_calc = ConfidenceCalculator()

        # Get must_include tokens from rewriter (if available)
        must_include = []
        rewrite_result = None
        if self.rewriter:
            rewrite_result = self.rewriter.rewrite(query, history)
            must_include = rewrite_result.must_include or []
            metrics.rewrite_used = rewrite_result.rewrite_used
            metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
            metrics.original_query = query
            metrics.rewritten_query = rewrite_result.standalone_query

        # Track escalation path and reason codes for decision trace
        escalation_path = []
        reason_codes = []  # NEW: Decision trace
        final_results = []
        final_signals = None

        # === STEP A: rag_fusion with 2 queries ===
        escalation_path.append("A")
        step_config = EscalationPolicy.get_step_config("A")

        result_a = await self._execute_fusion_step(
            query=query,
            k=k,
            num_queries=step_config["num_queries"],
            k_multiplier=step_config["k_multiplier"],
            collections=collections,
            where_filter=where_filter,
            rewrite_result=rewrite_result,
        )

        # Compute confidence signals - NOW with original_query for lexical overlap
        fusion_metrics_dict = {
            "fusion_gain": result_a.metrics.fusion_gain,
            "overlap_ratio": result_a.metrics.overlap_ratio,
        }
        signals_a = confidence_calc.compute(
            results=[r.__dict__ if hasattr(r, '__dict__') else r for r in result_a.results],
            must_include=must_include,
            fusion_metrics=fusion_metrics_dict,
            original_query=query,  # NEW: Pass query for lexical overlap
        )

        should_escalate, reason = confidence_calc.should_escalate(signals_a)
        reason_codes.append(f"A: {reason}")

        if not should_escalate:
            # Step A is sufficient
            logger.info(f"Adaptive: Step A OK (confidence={signals_a.overall_confidence:.2f})")
            final_results = result_a.results
            final_signals = signals_a
        else:
            logger.info(f"Adaptive: Escalating from A ({reason})")

            # === STEP B: increase k, search more collections ===
            escalation_path.append("B")
            step_config = EscalationPolicy.get_step_config("B")

            result_b = await self._execute_fusion_step(
                query=query,
                k=k,
                num_queries=step_config["num_queries"],
                k_multiplier=step_config["k_multiplier"],
                collections=None,  # Search all available
                where_filter=where_filter,
                rewrite_result=rewrite_result,
            )

            fusion_metrics_dict = {
                "fusion_gain": result_b.metrics.fusion_gain,
                "overlap_ratio": result_b.metrics.overlap_ratio,
            }
            signals_b = confidence_calc.compute(
                results=[r.__dict__ if hasattr(r, '__dict__') else r for r in result_b.results],
                must_include=must_include,
                fusion_metrics=fusion_metrics_dict,
                original_query=query,  # NEW: Pass query for lexical overlap
            )

            should_escalate, reason = confidence_calc.should_escalate(signals_b)
            reason_codes.append(f"B: {reason}")

            if not should_escalate:
                logger.info(f"Adaptive: Step B OK (confidence={signals_b.overall_confidence:.2f})")
                final_results = result_b.results
                final_signals = signals_b
            else:
                logger.info(f"Adaptive: Escalating from B ({reason})")

                # === STEP C: rag_fusion with 3 queries ===
                escalation_path.append("C")
                step_config = EscalationPolicy.get_step_config("C")

                result_c = await self._execute_fusion_step(
                    query=query,
                    k=k,
                    num_queries=step_config["num_queries"],
                    k_multiplier=step_config["k_multiplier"],
                    collections=None,
                    where_filter=where_filter,
                    rewrite_result=rewrite_result,
                )

                fusion_metrics_dict = {
                    "fusion_gain": result_c.metrics.fusion_gain,
                    "overlap_ratio": result_c.metrics.overlap_ratio,
                }
                signals_c = confidence_calc.compute(
                    results=[r.__dict__ if hasattr(r, '__dict__') else r for r in result_c.results],
                    must_include=must_include,
                    fusion_metrics=fusion_metrics_dict,
                    original_query=query,  # NEW: Pass query for lexical overlap
                )

                should_escalate, reason = confidence_calc.should_escalate(signals_c)
                reason_codes.append(f"C: {reason}")

                if not should_escalate:
                    logger.info(f"Adaptive: Step C OK (confidence={signals_c.overall_confidence:.2f})")
                    final_results = result_c.results
                    final_signals = signals_c
                else:
                    logger.warning(f"Adaptive: Escalating to fallback D ({reason})")

                    # === STEP D: Fallback ===
                    escalation_path.append("D")
                    reason_codes.append(f"D: fallback triggered")
                    metrics.fallback_triggered = True

                    # Use Step C results but mark as low confidence
                    final_results = result_c.results
                    final_signals = signals_c
                    final_signals.confidence_tier = "very_low"

        # === NO-ANSWER POLICY ===
        # Check if we should abstain after final step (gibberish detection, very low confidence)
        is_final = escalation_path[-1] == "D" if escalation_path else False
        if final_signals:
            should_abstain, abstain_reason = confidence_calc.should_abstain(
                final_signals,
                is_final_step=is_final
            )
            if should_abstain:
                final_signals.should_abstain = True
                final_signals.abstain_reason = abstain_reason
                reason_codes.append(f"ABSTAIN: {abstain_reason}")
                logger.warning(
                    f"Adaptive: Abstaining from answer ({abstain_reason}), "
                    f"lexical_overlap={final_signals.lexical_overlap:.2f}"
                )

        # Build final metrics
        metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000
        metrics.escalation_path = escalation_path
        metrics.final_step = escalation_path[-1] if escalation_path else ""
        metrics.confidence_signals = final_signals.to_dict() if final_signals else None
        metrics.reason_codes = reason_codes  # Decision trace for debugging

        conf_score = final_signals.overall_confidence if final_signals else 0.0
        lexical_score = final_signals.lexical_overlap if final_signals else 0.0
        abstain_flag = final_signals.should_abstain if final_signals else False

        logger.info(
            f"Adaptive complete: {len(final_results)} results in {metrics.total_latency_ms:.1f}ms "
            f"(path: {'→'.join(escalation_path)}, conf: {conf_score:.2f}, "
            f"lexical: {lexical_score:.2f}, abstain: {abstain_flag})"
        )

        return RetrievalResult(
            results=final_results,
            metrics=metrics,
            success=True,
        )

    async def _execute_fusion_step(
        self,
        query: str,
        k: int,
        num_queries: int,
        k_multiplier: float,
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
        rewrite_result,
    ) -> RetrievalResult:
        """
        Execute a single fusion retrieval step.

        This is a helper for _search_adaptive that runs rag_fusion
        with configurable num_queries and k_multiplier.
        """
        metrics = RetrievalMetrics(strategy="adaptive_step")

        # Use rewritten query if available
        search_query = query
        if rewrite_result:
            search_query = rewrite_result.standalone_query

        # Expand queries (limit to num_queries)
        if rewrite_result:
            expanded = self.expander.expand(search_query, rewrite_result, num_queries=num_queries)
        else:
            from dataclasses import dataclass

            @dataclass
            class MinimalRewriteResult:
                standalone_query: str = ""
                lexical_query: str = ""
                detected_entities: list = None

                def __post_init__(self):
                    if self.detected_entities is None:
                        self.detected_entities = []

            minimal = MinimalRewriteResult(standalone_query=search_query)
            expanded = self.expander.expand(search_query, minimal, num_queries=num_queries)

        metrics.num_queries = len(expanded.queries)
        metrics.query_variants = expanded.queries

        # Batch embed
        query_embeddings = self.embed_fn(expanded.queries)

        # Adjusted k for this step
        adjusted_k = int(k * k_multiplier)
        collection_names = collections or self.DEFAULT_COLLECTIONS

        # Search each embedding in parallel
        async def search_single_embedding(embedding: List[float]) -> List[Dict]:
            async with self._query_semaphore:
                results, _ = await parallel_collection_search(
                    client=self.client,
                    query_embedding=embedding,
                    collection_names=collection_names,
                    n_results_per_collection=adjusted_k,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )
                return results

        tasks = [search_single_embedding(emb) for emb in query_embeddings]
        result_sets = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter exceptions
        valid_result_sets = []
        for result in result_sets:
            if isinstance(result, Exception):
                valid_result_sets.append([])
            else:
                valid_result_sets.append(result)

        metrics.per_query_result_counts = [len(rs) for rs in valid_result_sets]

        # RRF merge
        merged_results = reciprocal_rank_fusion(valid_result_sets, k=60.0)

        # Calculate fusion metrics
        fusion_metrics = calculate_fusion_metrics(
            result_sets=valid_result_sets,
            merged_results=merged_results,
            expanded_queries=expanded,
        )

        metrics.fusion_used = True
        metrics.unique_docs_before_fusion = fusion_metrics.unique_docs_before_fusion
        metrics.unique_docs_after_fusion = fusion_metrics.unique_docs_after_fusion
        metrics.overlap_ratio = fusion_metrics.overlap_ratio
        metrics.fusion_gain = fusion_metrics.fusion_gain

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                id=r["id"],
                title=r.get("title", "Untitled"),
                snippet=r.get("snippet", ""),
                score=r.get("rrf_score", r.get("score", 0.0)),
                source=r.get("source", "unknown"),
                doc_type=r.get("doc_type"),
                date=r.get("date"),
                retriever="adaptive",
            )
            for r in merged_results[:k]
        ]

        return RetrievalResult(
            results=search_results,
            metrics=metrics,
            success=True,
        )
