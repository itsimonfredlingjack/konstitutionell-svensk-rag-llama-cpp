"""
RAG-Fusion - Phase 3: Multi-Query Retrieval with Reciprocal Rank Fusion
========================================================================

Generates multiple query variants and merges results using RRF for improved recall.

Key components:
- QueryExpander: Generates Q0 (semantic), Q1 (lexical), Q2 (paraphrase)
- reciprocal_rank_fusion: RRF merge with configurable k
- hybrid_reciprocal_rank_fusion: Dense + BM25 with weighted RRF
- calculate_fusion_metrics: Tracks overlap, gain, unique docs

Reference:
- Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet..."
- k=60 is the original paper default; we use k=30 for legal precision
- bm25_weight=1.5 favors exact term matches for legal documents
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("constitutional.rag_fusion")


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ExpandedQueries:
    """Result of query expansion for RAG-Fusion."""

    original: str
    queries: List[str]  # [Q0, Q1, Q2, ...]
    query_types: List[str]  # ["semantic", "lexical", "paraphrase"]
    expansion_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "original": self.original,
            "queries": self.queries,
            "query_types": self.query_types,
            "num_queries": len(self.queries),
            "expansion_latency_ms": round(self.expansion_latency_ms, 2),
        }


@dataclass
class FusionMetrics:
    """Metrics for RAG-Fusion retrieval."""

    fusion_used: bool = True
    num_queries: int = 1
    query_variants: List[str] = field(default_factory=list)
    per_query_result_counts: List[int] = field(default_factory=list)
    unique_docs_before_fusion: int = 0  # Docs in Q0 only
    unique_docs_after_fusion: int = 0  # Docs in merged result
    overlap_count: int = 0  # Docs appearing in 2+ queries
    overlap_ratio: float = 0.0  # overlap_count / unique_docs_after
    fusion_gain: float = 0.0  # % increase in unique docs
    rrf_latency_ms: float = 0.0
    expansion_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "fusion_used": self.fusion_used,
            "num_queries": self.num_queries,
            "query_variants": self.query_variants,
            "per_query_result_counts": self.per_query_result_counts,
            "unique_docs": {
                "before_fusion": self.unique_docs_before_fusion,
                "after_fusion": self.unique_docs_after_fusion,
            },
            "overlap": {
                "count": self.overlap_count,
                "ratio": round(self.overlap_ratio, 4),
            },
            "fusion_gain": round(self.fusion_gain, 4),
            "latency": {
                "expansion_ms": round(self.expansion_latency_ms, 2),
                "rrf_ms": round(self.rrf_latency_ms, 2),
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# QUERY EXPANDER
# ═══════════════════════════════════════════════════════════════════════════

# Swedish question patterns for paraphrasing
QUESTION_PATTERNS = [
    (r"^vad säger (.+?) om (.+)\?*$", "{0} {1}"),  # "Vad säger X om Y?" → "X Y"
    (r"^hur fungerar (.+)\?*$", "{0} funktioner egenskaper"),  # "Hur fungerar X?" → "X funktioner"
    (r"^vilka (.+?) finns i (.+)\?*$", "{1} {0}"),  # "Vilka X finns i Y?" → "Y X"
    (r"^vad är (.+)\?*$", "{0} definition betydelse"),  # "Vad är X?" → "X definition"
    (
        r"^när gäller (.+)\?*$",
        "{0} tillämpning ikraftträdande",
    ),  # "När gäller X?" → "X tillämpning"
    (r"^vem ansvarar för (.+)\?*$", "{0} ansvar myndighet"),  # "Vem ansvarar för X?" → "X ansvar"
]

# Swedish legal context words to add for paraphrasing
LEGAL_CONTEXT_WORDS = {
    "GDPR": ["dataskydd", "personuppgifter", "integritet"],
    "OSL": ["sekretess", "offentlighet", "allmän handling"],
    "RF": ["grundlag", "regeringsform", "konstitution"],
    "TF": ["tryckfrihet", "yttrandefrihet", "press"],
    "YGL": ["yttrandefrihet", "media", "radio", "tv"],
    "SoL": ["socialtjänst", "bistånd", "omsorg"],
    "LAS": ["anställning", "uppsägning", "arbetsrätt"],
    "PBL": ["bygglov", "detaljplan", "planering"],
}


class QueryExpander:
    """
    Generates multiple query variants for RAG-Fusion.

    Usage:
        expander = QueryExpander()
        expanded = expander.expand("Vad säger GDPR?", rewrite_result)
        # expanded.queries = ["Vad säger GDPR?", "GDPR dataskydd", "GDPR personuppgifter"]
    """

    def __init__(self, max_queries: int = 3):
        """
        Initialize QueryExpander.

        Args:
            max_queries: Maximum number of query variants to generate (default: 3)
        """
        self.max_queries = max_queries
        self._question_patterns = [
            (re.compile(pattern, re.IGNORECASE), template)
            for pattern, template in QUESTION_PATTERNS
        ]

    def expand(
        self,
        query: str,
        rewrite_result: Any,  # RewriteResult from query_rewriter
        num_queries: Optional[int] = None,
    ) -> ExpandedQueries:
        """
        Generate query variants for RAG-Fusion.

        Args:
            query: Standalone query (after Phase 2 decontextualization)
            rewrite_result: RewriteResult from QueryRewriter
            num_queries: Override max_queries for this call

        Returns:
            ExpandedQueries with Q0 (semantic), Q1 (lexical), Q2 (paraphrase)
        """
        start = time.perf_counter()
        max_q = num_queries or self.max_queries

        queries = [query]  # Q0 = original (semantic)
        types = ["semantic"]

        # Q1: Lexical variant from RewriteResult.lexical_query
        if hasattr(rewrite_result, "lexical_query") and rewrite_result.lexical_query:
            lexical = rewrite_result.lexical_query.strip()
            if lexical and lexical != query:
                queries.append(lexical)
                types.append("lexical")

        # Q2: Paraphrase (rule-based)
        if len(queries) < max_q:
            entities = getattr(rewrite_result, "detected_entities", [])
            paraphrase = self._generate_paraphrase(query, entities)
            if paraphrase and paraphrase not in queries:
                queries.append(paraphrase)
                types.append("paraphrase")

        latency_ms = (time.perf_counter() - start) * 1000

        result = ExpandedQueries(
            original=query,
            queries=queries[:max_q],
            query_types=types[:max_q],
            expansion_latency_ms=latency_ms,
        )

        logger.info(
            f"Query expansion: '{query[:50]}...' → {len(result.queries)} variants "
            f"(latency: {latency_ms:.2f}ms)"
        )

        return result

    def _generate_paraphrase(
        self,
        query: str,
        entities: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Generate a rule-based paraphrase of the query.

        Strategies:
        1. Question → keyword transformation
        2. Entity-focused reformulation with legal context

        Args:
            query: Original query
            entities: Detected entities from RewriteResult

        Returns:
            Paraphrased query or None if no good paraphrase found
        """
        query_lower = query.lower().strip()

        # Strategy 1: Question pattern matching
        for pattern, template in self._question_patterns:
            match = pattern.match(query_lower)
            if match:
                groups = match.groups()
                try:
                    paraphrase = template.format(*groups)
                    return paraphrase.strip()
                except (IndexError, KeyError):
                    continue

        # Strategy 2: Entity-focused reformulation
        entity_values = [e.get("value", "") for e in entities if e.get("type") == "lag"]

        if entity_values:
            # Find the first known law and add context words
            for entity in entity_values:
                entity_upper = entity.upper()
                if entity_upper in LEGAL_CONTEXT_WORDS:
                    context_words = LEGAL_CONTEXT_WORDS[entity_upper][:2]
                    # Remove question words and build keyword query
                    keywords = self._extract_keywords(query)
                    return f"{entity} {' '.join(context_words)} {' '.join(keywords)}"

        # Strategy 3: Simple keyword extraction for short queries
        if len(query.split()) <= 5:
            keywords = self._extract_keywords(query)
            if keywords:
                return " ".join(keywords)

        return None

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract significant keywords from query, removing stopwords."""
        stopwords = {
            "vad",
            "hur",
            "när",
            "var",
            "vilka",
            "vilken",
            "vilket",
            "är",
            "finns",
            "gäller",
            "säger",
            "innebär",
            "betyder",
            "om",
            "i",
            "på",
            "för",
            "med",
            "av",
            "till",
            "den",
            "det",
            "och",
            "eller",
            "som",
            "att",
            "kan",
            "ska",
            "måste",
        }

        words = re.findall(r"\b\w+\b", query.lower())
        keywords = [w for w in words if w not in stopwords and len(w) > 2]

        return keywords


# ═══════════════════════════════════════════════════════════════════════════
# RECIPROCAL RANK FUSION
# ═══════════════════════════════════════════════════════════════════════════


def reciprocal_rank_fusion(
    result_sets: List[List[Dict[str, Any]]],
    k: float = 60.0,
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion algorithm.

    For each document d:
        RRF(d) = Σ 1/(k + rank_i(d))

    where rank_i is the rank of d in result set i (1-indexed).
    Documents not in a result set get rank = infinity (no contribution).

    Args:
        result_sets: List of result sets, each from a different query variant
        k: RRF constant (default: 60, from original paper)

    Returns:
        Merged results sorted by RRF score (descending)

    Reference:
        Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet
        and individual rank learning methods"
    """
    if not result_sets:
        return []

    doc_scores: Dict[str, float] = {}
    doc_data: Dict[str, Dict[str, Any]] = {}
    doc_appearances: Dict[str, int] = {}  # Track how many queries returned this doc

    for query_idx, results in enumerate(result_sets):
        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get("id", "")
            if not doc_id:
                continue

            # Calculate RRF contribution
            rrf_contribution = 1.0 / (k + rank)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_contribution

            # Track appearances
            doc_appearances[doc_id] = doc_appearances.get(doc_id, 0) + 1

            # Keep doc data (first occurrence wins for metadata)
            if doc_id not in doc_data:
                doc_data[doc_id] = doc.copy()

    # Sort by RRF score (descending)
    sorted_ids = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)

    # Build result list with RRF scores
    merged_results = []
    for doc_id in sorted_ids:
        doc = doc_data[doc_id].copy()
        doc["rrf_score"] = doc_scores[doc_id]
        doc["original_score"] = doc.get("score", 0.0)
        doc["query_appearances"] = doc_appearances[doc_id]
        merged_results.append(doc)

    return merged_results


# ═══════════════════════════════════════════════════════════════════════════
# FUSION METRICS
# ═══════════════════════════════════════════════════════════════════════════


def calculate_fusion_metrics(
    result_sets: List[List[Dict[str, Any]]],
    merged_results: List[Dict[str, Any]],
    expanded_queries: Optional[ExpandedQueries] = None,
) -> FusionMetrics:
    """
    Calculate metrics for RAG-Fusion retrieval.

    Args:
        result_sets: Original result sets from each query variant
        merged_results: RRF-merged results
        expanded_queries: Optional ExpandedQueries for additional metadata

    Returns:
        FusionMetrics with overlap, gain, and timing data
    """
    if not result_sets:
        return FusionMetrics(fusion_used=False)

    # Count unique docs before fusion (Q0 only)
    q0_ids = {doc.get("id") for doc in result_sets[0] if doc.get("id")}
    unique_before = len(q0_ids)

    # Count unique docs after fusion
    all_ids: Set[str] = set()
    for results in result_sets:
        for doc in results:
            doc_id = doc.get("id")
            if doc_id:
                all_ids.add(doc_id)
    unique_after = len(all_ids)

    # Count overlapping docs (appear in 2+ result sets)
    doc_counts: Dict[str, int] = {}
    for results in result_sets:
        seen_in_this_set: Set[str] = set()
        for doc in results:
            doc_id = doc.get("id")
            if doc_id and doc_id not in seen_in_this_set:
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
                seen_in_this_set.add(doc_id)

    overlap_count = sum(1 for count in doc_counts.values() if count >= 2)
    overlap_ratio = overlap_count / unique_after if unique_after > 0 else 0.0

    # Calculate fusion gain (% increase in unique docs)
    fusion_gain = (unique_after - unique_before) / unique_before if unique_before > 0 else 0.0

    # Per-query result counts
    per_query_counts = [len(results) for results in result_sets]

    metrics = FusionMetrics(
        fusion_used=True,
        num_queries=len(result_sets),
        per_query_result_counts=per_query_counts,
        unique_docs_before_fusion=unique_before,
        unique_docs_after_fusion=unique_after,
        overlap_count=overlap_count,
        overlap_ratio=overlap_ratio,
        fusion_gain=fusion_gain,
    )

    # Add query variants if available
    if expanded_queries:
        metrics.query_variants = expanded_queries.queries
        metrics.expansion_latency_ms = expanded_queries.expansion_latency_ms

    logger.info(
        f"Fusion metrics: {unique_before} → {unique_after} docs "
        f"(gain: {fusion_gain:.1%}, overlap: {overlap_ratio:.1%})"
    )

    return metrics


# ═══════════════════════════════════════════════════════════════════════════
# GUARDRAILS
# ═══════════════════════════════════════════════════════════════════════════

# Pattern for Swedish SFS numbers
SFS_PATTERN = re.compile(r"\b(\d{4}:\d+)\b")


def validate_no_hallucinated_entities(
    original_query: str,
    expanded_queries: List[str],
    detected_entities: List[Dict[str, Any]],
) -> bool:
    """
    Guardrail: Ensure expanded queries don't introduce new SFS numbers.

    Args:
        original_query: The original user query
        expanded_queries: List of expanded query variants
        detected_entities: Entities from the original query

    Returns:
        True if valid (no hallucination), False otherwise
    """
    # Extract SFS numbers from original query and entities
    original_sfs = set(SFS_PATTERN.findall(original_query))
    for entity in detected_entities:
        if entity.get("type") == "sfs":
            original_sfs.add(entity.get("value", ""))

    # Check expanded queries for new SFS numbers
    for i, query in enumerate(expanded_queries[1:], start=1):  # Skip Q0
        new_sfs = set(SFS_PATTERN.findall(query))
        hallucinated = new_sfs - original_sfs

        if hallucinated:
            logger.warning(f"Guardrail blocked: Q{i} contains hallucinated SFS: {hallucinated}")
            return False

    return True


def should_use_fusion_results(
    result_sets: List[List[Dict[str, Any]]],
    min_gain_threshold: float = 0.05,
) -> bool:
    """
    Guardrail: Only use fusion if it provides meaningful value.

    Args:
        result_sets: Result sets from each query variant
        min_gain_threshold: Minimum fusion gain to justify cost (default: 5%)

    Returns:
        True if fusion provides value, False if Q0 results are sufficient
    """
    if not result_sets or len(result_sets) < 2:
        return False

    # Calculate gain
    q0_ids = {doc.get("id") for doc in result_sets[0] if doc.get("id")}
    all_ids: Set[str] = set()
    for results in result_sets:
        for doc in results:
            if doc.get("id"):
                all_ids.add(doc.get("id"))

    unique_before = len(q0_ids)
    unique_after = len(all_ids)

    if unique_before == 0:
        return True  # No Q0 results, fusion might help

    gain = (unique_after - unique_before) / unique_before

    if gain < min_gain_threshold:
        logger.info(
            f"Low fusion gain ({gain:.1%} < {min_gain_threshold:.0%}), "
            "consider Q0-only for performance"
        )

    return gain >= min_gain_threshold


# ═══════════════════════════════════════════════════════════════════════════
# HYBRID RRF (DENSE + BM25)
# ═══════════════════════════════════════════════════════════════════════════


def hybrid_reciprocal_rank_fusion(
    dense_result_sets: List[List[Dict[str, Any]]],
    bm25_results: Optional[List[Dict[str, Any]]] = None,
    k: float = 60.0,
    bm25_weight: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Hybrid RRF that combines dense and BM25 results.

    This extends standard RRF by treating BM25 results as an additional
    result set with configurable weighting.

    Args:
        dense_result_sets: List of result sets from dense queries (Q0, Q1, Q2, ...)
        bm25_results: Optional results from BM25 lexical search
        k: RRF constant (default: 60)
        bm25_weight: Weight multiplier for BM25 contributions (default: 1.0)
            - Use 1.5 for legal docs with exact terms
            - Use 0.7 for conceptual queries

    Returns:
        Merged results sorted by hybrid RRF score

    Example:
        # Dense: 3 query variants
        # BM25: 1 lexical search
        # Total: 4 result sets in RRF with BM25 having 1.5x weight
        merged = hybrid_reciprocal_rank_fusion(
            dense_result_sets=[q0_results, q1_results, q2_results],
            bm25_results=bm25_results,
            bm25_weight=1.5,
        )
    """
    if not dense_result_sets:
        if bm25_results:
            # Only BM25 results - return as-is with RRF scores
            return [
                {**doc, "rrf_score": 1.0 / (k + rank + 1), "query_appearances": 1}
                for rank, doc in enumerate(bm25_results)
            ]
        return []

    # Combine all result sets
    all_result_sets = list(dense_result_sets)
    bm25_index = None

    if bm25_results:
        bm25_index = len(all_result_sets)
        all_result_sets.append(bm25_results)

    # RRF scoring with optional BM25 weight
    doc_scores: Dict[str, float] = {}
    doc_data: Dict[str, Dict[str, Any]] = {}
    doc_appearances: Dict[str, int] = {}
    doc_sources: Dict[str, Set[str]] = {}  # Track which retrievers found each doc

    for set_idx, results in enumerate(all_result_sets):
        is_bm25 = (set_idx == bm25_index) if bm25_index is not None else False
        weight = bm25_weight if is_bm25 else 1.0
        source_tag = "bm25" if is_bm25 else f"dense_q{set_idx}"

        for rank, doc in enumerate(results, start=1):
            doc_id = doc.get("id", "")
            if not doc_id:
                continue

            # Calculate weighted RRF contribution
            rrf_contribution = weight * (1.0 / (k + rank))
            doc_scores[doc_id] = doc_scores.get(doc_id, 0.0) + rrf_contribution

            # Track appearances and sources
            doc_appearances[doc_id] = doc_appearances.get(doc_id, 0) + 1
            if doc_id not in doc_sources:
                doc_sources[doc_id] = set()
            doc_sources[doc_id].add(source_tag)

            # Keep doc data (first occurrence wins for metadata)
            if doc_id not in doc_data:
                normalized_doc = doc.copy()

                # BM25 often has id/text only; normalize into retrieval schema so
                # downstream grading/reranking always gets non-empty snippets.
                text = str(normalized_doc.get("text", "") or "").strip()
                if not normalized_doc.get("snippet") and text:
                    normalized_doc["snippet"] = text[:1200] + "..." if len(text) > 1200 else text
                if not normalized_doc.get("title"):
                    normalized_doc["title"] = normalized_doc.get("id", "Untitled")
                if not normalized_doc.get("source"):
                    normalized_doc["source"] = "bm25" if is_bm25 else "unknown"

                doc_data[doc_id] = normalized_doc

    # Sort by RRF score (descending)
    sorted_ids = sorted(doc_scores.keys(), key=lambda x: doc_scores[x], reverse=True)

    # Build result list with RRF scores and source tracking
    merged_results = []
    for doc_id in sorted_ids:
        doc = doc_data[doc_id].copy()
        doc["rrf_score"] = doc_scores[doc_id]
        doc["original_score"] = doc.get("score", 0.0)
        doc["query_appearances"] = doc_appearances[doc_id]
        doc["retriever_sources"] = list(doc_sources[doc_id])
        doc["found_by_bm25"] = "bm25" in doc_sources[doc_id]
        merged_results.append(doc)

    logger.info(
        f"Hybrid RRF: {len(dense_result_sets)} dense + "
        f"{'1 BM25' if bm25_results else '0 BM25'} → "
        f"{len(merged_results)} merged (BM25 weight: {bm25_weight})"
    )

    return merged_results
