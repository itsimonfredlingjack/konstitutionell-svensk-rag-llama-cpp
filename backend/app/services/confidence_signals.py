"""
Phase 4: Confidence Signals for Adaptive Retrieval
===================================================

Compute retrieval confidence WITHOUT additional LLM calls.
Signals derived from existing retrieval outputs:
  - Reranker signals: top_score, margin (top1 - top2)
  - Coverage signals: must_include hit rate
  - Fusion signals: fusion_gain, overlap_ratio
  - Diversity signals: near-duplicate detection

References:
  - Self-RAG: Learning to Retrieve, Generate, and Critique (Asai et al.)
  - Cormack & Clarke: RRF k=60 near-optimal
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# Default thresholds - CALIBRATED for RRF scores (k=60)
# RRF formula: 1/(k+rank), so top score at rank 1 = 1/61 ≈ 0.016
# With 2 queries at rank 1: 2/61 ≈ 0.033, with 3: 3/61 ≈ 0.049
DEFAULT_THRESHOLDS = {
    "top_score_low": 0.025,  # Below this = weak top result (< rank 2 in any query)
    "margin_low": 0.003,  # Below this = uncertain ranking (normalized margin)
    "must_include_min": 0.5,  # Below this = missing key entities
    "fusion_gain_low": 0.05,  # Below this = queries not adding value
    "overlap_high": 0.9,  # Above this + low scores = corpus lacks answer
    "near_duplicate_max": 0.7,  # Above this = too many duplicates
    "overall_confidence_low": 0.4,  # Below this = escalate
    # NEW: Query quality thresholds
    "lexical_overlap_min": 0.15,  # Below this = query tokens not in results (gibberish)
    "abstain_confidence": 0.25,  # Below this after max escalation = refuse to answer
    "empty_entities_penalty": 0.20,  # Penalty when no entities extracted from query
}


# ═══════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ConfidenceSignals:
    """
    All signals used to compute retrieval confidence.

    Each signal is 0.0-1.0 where higher = more confident.
    """

    # Reranker signals
    top_score: float = 0.0  # Normalized score of best result
    margin: float = 0.0  # Difference between top1 and top2

    # Coverage signals
    must_include_hit_rate: float = 0.0  # Fraction of must_include found in top-k
    must_include_total: int = 0  # Total must_include tokens
    must_include_found: int = 0  # How many were found

    # Fusion signals (from Phase 3)
    fusion_gain: float = 0.0  # % increase in unique docs
    overlap_ratio: float = 0.0  # % docs appearing in multiple queries

    # Diversity signals
    near_duplicate_ratio: float = 0.0  # Fraction of near-duplicate docs
    unique_sources: int = 0  # Number of unique document sources

    # NEW: Query quality signals
    lexical_overlap: float = 0.0  # Fraction of query tokens found in results
    query_token_count: int = 0  # Number of meaningful tokens in query
    has_extractable_entities: bool = True  # False = gibberish/nonsense query

    # Computed
    overall_confidence: float = 0.0  # Weighted combination
    confidence_tier: str = "unknown"  # "high", "medium", "low", "very_low"
    should_abstain: bool = False  # True = refuse to answer, ask for clarification
    abstain_reason: str = ""  # Why we're abstaining

    def to_dict(self) -> Dict:
        """Serialize for API response."""
        return {
            "top_score": round(self.top_score, 4),
            "margin": round(self.margin, 4),
            "must_include_hit_rate": round(self.must_include_hit_rate, 4),
            "must_include_found": f"{self.must_include_found}/{self.must_include_total}",
            "fusion_gain": round(self.fusion_gain, 4),
            "overlap_ratio": round(self.overlap_ratio, 4),
            "near_duplicate_ratio": round(self.near_duplicate_ratio, 4),
            "unique_sources": self.unique_sources,
            "lexical_overlap": round(self.lexical_overlap, 4),
            "query_token_count": self.query_token_count,
            "has_extractable_entities": self.has_extractable_entities,
            "overall_confidence": round(self.overall_confidence, 4),
            "confidence_tier": self.confidence_tier,
            "should_abstain": self.should_abstain,
            "abstain_reason": self.abstain_reason,
        }


@dataclass
class EscalationResult:
    """Result of an escalation attempt."""

    step: str  # "A", "B", "C", "D"
    strategy_used: str  # "rag_fusion", "rag_fusion_3q", etc.
    signals: ConfidenceSignals  # Signals after this step
    results: List[Dict] = field(default_factory=list)
    escalated: bool = False  # Whether we escalated from this step
    reason: str = ""  # Why we escalated (or didn't)


@dataclass
class AdaptiveResult:
    """Final result of adaptive retrieval."""

    results: List[Dict]
    signals: ConfidenceSignals
    escalation_path: List[str]  # ["A", "B"] = tried A, escalated to B
    final_step: str  # "A", "B", "C", or "D"
    final_strategy: str
    total_escalations: int = 0
    fallback_triggered: bool = False  # True if reached step D
    # NEW: Decision trace for debugging
    reason_codes: List[str] = field(default_factory=list)  # Why each decision was made
    query_analyzed: str = ""  # The query that was analyzed

    def to_dict(self) -> Dict:
        """Serialize for API response."""
        return {
            "signals": self.signals.to_dict(),
            "escalation_path": self.escalation_path,
            "final_step": self.final_step,
            "final_strategy": self.final_strategy,
            "total_escalations": self.total_escalations,
            "fallback_triggered": self.fallback_triggered,
            "reason_codes": self.reason_codes,
            "should_abstain": self.signals.should_abstain,
            "abstain_reason": self.signals.abstain_reason,
        }


# ═══════════════════════════════════════════════════════════════════════════
# SIGNAL COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════


class ConfidenceCalculator:
    """
    Compute confidence signals from retrieval results.

    No LLM calls - pure computation on existing data.
    """

    def __init__(self, thresholds: Optional[Dict] = None):
        self.thresholds = thresholds or DEFAULT_THRESHOLDS

    def compute(
        self,
        results: List[Dict],
        must_include: List[str],
        fusion_metrics: Optional[Dict] = None,
        original_query: str = "",
    ) -> ConfidenceSignals:
        """
        Compute all confidence signals.

        Args:
            results: Retrieved documents with scores
            must_include: Tokens that MUST appear in results (from rewriter)
            fusion_metrics: Fusion metrics from Phase 3 (if available)
            original_query: The original user query (for lexical overlap)

        Returns:
            ConfidenceSignals with all computed values
        """
        signals = ConfidenceSignals()

        if not results:
            signals.confidence_tier = "very_low"
            signals.should_abstain = True
            signals.abstain_reason = "no_results"
            return signals

        # 1. Reranker signals
        signals.top_score, signals.margin = self._compute_reranker_signals(results)

        # 2. Coverage signals
        hit_rate, found, total = self._compute_coverage_signals(results, must_include)
        signals.must_include_hit_rate = hit_rate
        signals.must_include_found = found
        signals.must_include_total = total

        # 3. Fusion signals (from Phase 3 if available)
        if fusion_metrics:
            signals.fusion_gain = fusion_metrics.get("fusion_gain", 0.0)
            signals.overlap_ratio = fusion_metrics.get("overlap_ratio", 0.0)

        # 4. Diversity signals
        signals.near_duplicate_ratio, signals.unique_sources = self._compute_diversity_signals(
            results
        )

        # 5. NEW: Query quality signals
        signals.lexical_overlap, signals.query_token_count = self._compute_lexical_overlap(
            results, original_query
        )
        signals.has_extractable_entities = len(must_include) > 0

        # BOOST: If must_include entities were found, that's strong evidence
        # the query is valid (even if the exact words aren't in results).
        # E.g., "dataskyddslagen 2018:218" - the word isn't in results but
        # the SFS number was found, so the query is clearly valid.
        if signals.must_include_hit_rate >= 0.5 and signals.has_extractable_entities:
            # Ensure lexical_overlap is at least half of must_include_hit_rate
            boosted_overlap = max(signals.lexical_overlap, signals.must_include_hit_rate * 0.5)
            signals.lexical_overlap = boosted_overlap

        # 6. Overall confidence (weighted combination, including query quality)
        signals.overall_confidence = self._compute_overall_confidence(signals)
        signals.confidence_tier = self._tier_from_score(signals.overall_confidence)

        return signals

    def _compute_reranker_signals(self, results: List[Dict]) -> tuple:
        """
        Compute top_score and margin from result scores.

        Uses 'score', 'rrf_score', or '_distance' fields.
        """
        if not results:
            return 0.0, 0.0

        # Extract scores (handle different field names)
        scores = []
        for doc in results[:10]:  # Only consider top 10
            score = doc.get("score") or doc.get("rrf_score") or 0.0
            # ChromaDB uses _distance (lower is better), convert to similarity
            if "_distance" in doc:
                score = 1.0 / (1.0 + doc["_distance"])
            scores.append(float(score))

        if not scores:
            return 0.0, 0.0

        # Normalize scores to 0-1 range
        max_score = max(scores) if scores else 0
        min_score = min(scores) if scores else 0

        # Top score (normalized)
        top_score = scores[0] if scores else 0.0

        # Margin: difference between top1 and top2
        if len(scores) >= 2:
            margin = scores[0] - scores[1]
        else:
            margin = scores[0]  # Only one result = full margin

        # Normalize margin relative to score range
        score_range = max_score - min_score if max_score > min_score else 1.0
        margin_normalized = margin / score_range if score_range > 0 else margin

        return min(top_score, 1.0), min(margin_normalized, 1.0)

    def _compute_coverage_signals(
        self,
        results: List[Dict],
        must_include: List[str],
    ) -> tuple:
        """
        Compute must_include hit rate.

        Returns (hit_rate, found_count, total_count)
        """
        if not must_include:
            return 1.0, 0, 0  # No requirements = fully satisfied

        # Combine text from top results
        # Handle both raw ChromaDB format and API response format
        combined_text = ""
        for doc in results[:10]:
            # Get text content (various field names)
            text = doc.get("text", "") or doc.get("content", "") or doc.get("snippet", "") or ""
            # Get title (can be direct or in metadata)
            title = doc.get("title", "")
            if not title:
                metadata = doc.get("metadata", {})
                title = metadata.get("title", "") if isinstance(metadata, dict) else ""
            combined_text += f" {text} {title} ".lower()

        # Check which must_include tokens are found
        found = 0
        for token in must_include:
            token_lower = token.lower()
            # Handle SFS numbers specially (e.g., "2018:218")
            if re.match(r"\d{4}:\d+", token):
                if token in combined_text:
                    found += 1
            elif token_lower in combined_text:
                found += 1

        total = len(must_include)
        hit_rate = found / total if total > 0 else 1.0

        return hit_rate, found, total

    def _compute_diversity_signals(self, results: List[Dict]) -> tuple:
        """
        Compute near-duplicate ratio and unique sources.

        Near-duplicates detected by title/content similarity.
        """
        if not results:
            return 0.0, 0

        # Track unique sources (doc_type, source combinations)
        sources = set()
        titles = []

        for doc in results[:10]:
            metadata = doc.get("metadata", {})
            if isinstance(metadata, dict):
                doc_type = metadata.get("doc_type", "unknown")
                source = metadata.get("source", "unknown")
                sources.add(f"{doc_type}:{source}")

                title = metadata.get("title", "")
                if title:
                    titles.append(title.lower()[:100])  # First 100 chars

        unique_sources = len(sources)

        # Near-duplicate detection: simple title prefix matching
        near_duplicates = 0
        seen_prefixes = set()
        for title in titles:
            prefix = title[:50]  # First 50 chars as fingerprint
            if prefix in seen_prefixes:
                near_duplicates += 1
            seen_prefixes.add(prefix)

        near_dup_ratio = near_duplicates / len(results) if results else 0.0

        return near_dup_ratio, unique_sources

    def _compute_lexical_overlap(
        self,
        results: List[Dict],
        query: str,
    ) -> tuple:
        """
        Compute lexical overlap between query tokens and result content.

        This catches gibberish/nonsense queries like "NONEXISTENT_QUERY_12345"
        that produce low-relevance results but might still get moderate
        confidence from other signals.

        Returns (overlap_ratio, token_count)
        """
        if not query:
            return 0.0, 0

        # Tokenize query: extract meaningful words (>2 chars, alphanumeric)
        # Swedish stopwords are kept intentionally - they help detect gibberish
        query_lower = query.lower()
        query_tokens = set(
            token
            for token in re.findall(r"\b\w+\b", query_lower)
            if len(token) > 2 and not token.isdigit()
        )

        if not query_tokens:
            return 0.0, 0

        # Combine text from top results
        combined_text = ""
        for doc in results[:10]:
            text = doc.get("text", "") or doc.get("content", "") or doc.get("snippet", "") or ""
            title = doc.get("title", "")
            if not title:
                metadata = doc.get("metadata", {})
                title = metadata.get("title", "") if isinstance(metadata, dict) else ""
            combined_text += f" {text} {title} ".lower()

        # Count how many query tokens appear in results
        found_tokens = 0
        for token in query_tokens:
            if token in combined_text:
                found_tokens += 1

        overlap_ratio = found_tokens / len(query_tokens) if query_tokens else 0.0

        return overlap_ratio, len(query_tokens)

    def _compute_overall_confidence(self, signals: ConfidenceSignals) -> float:
        """
        Weighted combination of all signals.

        Weights reflect importance:
        - must_include_hit_rate: Critical (if specified, must find)
        - lexical_overlap: Critical (catches gibberish queries)
        - top_score: Very important (quality of best match)
        - margin: Important (certainty of ranking)
        - near_duplicate_ratio: Moderate (diversity needed)
        - fusion signals: Moderate (multi-query agreement)
        """
        weights = {
            "top_score": 0.20,
            "margin": 0.10,
            "must_include_hit_rate": 0.25,  # Critical
            "lexical_overlap": 0.20,  # NEW: Critical for gibberish detection
            "near_duplicate_penalty": 0.10,
            "fusion_agreement": 0.15,  # overlap_ratio as agreement signal
        }

        # Convert near_duplicate_ratio to a "diversity score" (inverse)
        diversity_score = 1.0 - signals.near_duplicate_ratio

        # Fusion agreement: high overlap = queries agree = good
        # But only if we have fusion data
        fusion_agreement = signals.overlap_ratio if signals.overlap_ratio > 0 else 0.5

        # Weighted sum
        confidence = (
            weights["top_score"] * signals.top_score
            + weights["margin"] * signals.margin
            + weights["must_include_hit_rate"] * signals.must_include_hit_rate
            + weights["lexical_overlap"] * signals.lexical_overlap
            + weights["near_duplicate_penalty"] * diversity_score
            + weights["fusion_agreement"] * fusion_agreement
        )

        # PENALTY: No extractable entities = likely gibberish
        # Apply penalty if query has tokens but no entities were extracted
        if not signals.has_extractable_entities and signals.query_token_count > 0:
            penalty = self.thresholds.get("empty_entities_penalty", 0.20)
            confidence -= penalty

        # Clamp to 0-1
        return max(0.0, min(1.0, confidence))

    def _tier_from_score(self, score: float) -> str:
        """Convert confidence score to tier label."""
        if score >= 0.7:
            return "high"
        elif score >= 0.5:
            return "medium"
        elif score >= 0.3:
            return "low"
        else:
            return "very_low"

    def should_escalate(self, signals: ConfidenceSignals) -> tuple:
        """
        Determine if escalation is needed.

        Returns (should_escalate: bool, reason: str)
        """
        reasons = []

        # Check individual thresholds
        if signals.top_score < self.thresholds["top_score_low"]:
            reasons.append(f"top_score={signals.top_score:.3f}<{self.thresholds['top_score_low']}")

        if signals.margin < self.thresholds["margin_low"]:
            reasons.append(f"margin={signals.margin:.3f}<{self.thresholds['margin_low']}")

        if signals.must_include_total > 0:
            if signals.must_include_hit_rate < self.thresholds["must_include_min"]:
                reasons.append(
                    f"must_include={signals.must_include_found}/{signals.must_include_total}"
                )

        if signals.near_duplicate_ratio > self.thresholds["near_duplicate_max"]:
            reasons.append(f"duplicates={signals.near_duplicate_ratio:.2f}")

        # NEW: Check lexical overlap (catches gibberish)
        if signals.lexical_overlap < self.thresholds["lexical_overlap_min"]:
            reasons.append(
                f"lexical_overlap={signals.lexical_overlap:.2f}<{self.thresholds['lexical_overlap_min']}"
            )

        # Overall confidence check
        if signals.overall_confidence < self.thresholds["overall_confidence_low"]:
            reasons.append(f"overall={signals.overall_confidence:.2f}")

        should_escalate = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else "confidence OK"

        return should_escalate, reason

    def should_abstain(self, signals: ConfidenceSignals, is_final_step: bool = False) -> tuple:
        """
        Determine if we should refuse to answer (no-answer policy).

        Called after max escalation or when signals indicate gibberish.

        Returns (should_abstain: bool, reason: str)
        """
        reasons = []

        # Hard abstain: very low lexical overlap = gibberish query
        if signals.lexical_overlap < 0.05:
            reasons.append("gibberish_query")

        # Hard abstain: no results at all
        if signals.top_score == 0.0:
            reasons.append("no_results")

        # Soft abstain after final step: confidence still below abstain threshold
        if is_final_step:
            abstain_threshold = self.thresholds.get("abstain_confidence", 0.25)
            if signals.overall_confidence < abstain_threshold:
                reasons.append(f"confidence={signals.overall_confidence:.2f}<{abstain_threshold}")

            # Also abstain if no entities AND low lexical overlap
            if not signals.has_extractable_entities and signals.lexical_overlap < 0.3:
                reasons.append("no_entities_low_overlap")

        should_abstain = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else ""

        return should_abstain, reason


# ═══════════════════════════════════════════════════════════════════════════
# ESCALATION POLICIES
# ═══════════════════════════════════════════════════════════════════════════


class EscalationPolicy:
    """
    Define escalation steps for adaptive retrieval.

    Step A: rag_fusion with 2 queries (Q0+Q1)
    Step B: increase k_pre_rerank, search more collections
    Step C: rag_fusion with 3 queries (add Q2)
    Step D: fallback (ask for clarification)
    """

    # Step configurations
    STEPS = {
        "A": {
            "strategy": "rag_fusion",
            "num_queries": 2,
            "k_multiplier": 1.0,
            "collections": None,  # Default
        },
        "B": {
            "strategy": "rag_fusion",
            "num_queries": 2,
            "k_multiplier": 2.0,  # Double the candidates
            "collections": None,  # All available
        },
        "C": {
            "strategy": "rag_fusion",
            "num_queries": 3,  # Add Q2
            "k_multiplier": 2.0,
            "collections": None,
        },
        "D": {
            "strategy": "fallback",
            "num_queries": 3,
            "k_multiplier": 3.0,
            "collections": None,
            "fallback": True,
        },
    }

    @classmethod
    def get_step_config(cls, step: str) -> Dict:
        """Get configuration for a specific step."""
        return cls.STEPS.get(step, cls.STEPS["A"])

    @classmethod
    def next_step(cls, current: str) -> Optional[str]:
        """Get next escalation step, or None if at end."""
        steps = list(cls.STEPS.keys())
        try:
            idx = steps.index(current)
            if idx < len(steps) - 1:
                return steps[idx + 1]
        except ValueError:
            pass
        return None

    @classmethod
    def all_steps(cls) -> List[str]:
        """Return all step names in order."""
        return list(cls.STEPS.keys())
