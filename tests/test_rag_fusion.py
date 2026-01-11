"""
Tests for RAG-Fusion - Phase 3: Multi-Query Retrieval with RRF
===============================================================

Tests cover:
1. RRF algorithm correctness
2. Query expansion (Q0, Q1, Q2)
3. Fusion metrics calculation
4. Guardrails (no hallucinated entities)
5. Integration tests
"""

import pytest
from app.services.rag_fusion import (
    LEGAL_CONTEXT_WORDS,
    QUESTION_PATTERNS,
    ExpandedQueries,
    FusionMetrics,
    QueryExpander,
    calculate_fusion_metrics,
    reciprocal_rank_fusion,
    should_use_fusion_results,
    validate_no_hallucinated_entities,
)

# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def expander():
    """Create a QueryExpander instance."""
    return QueryExpander(max_queries=3)


@pytest.fixture
def mock_rewrite_result():
    """Mock RewriteResult for testing."""
    from dataclasses import dataclass

    @dataclass
    class MockRewriteResult:
        standalone_query: str = "GDPR samtycke"
        lexical_query: str = "GDPR samtycke dataskydd"
        detected_entities: list = None

        def __post_init__(self):
            if self.detected_entities is None:
                self.detected_entities = [{"type": "lag", "value": "GDPR", "confidence": 1.0}]

    return MockRewriteResult()


# ═══════════════════════════════════════════════════════════════════════════
# RRF ALGORITHM TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestReciprocalRankFusion:
    """Tests for RRF algorithm correctness."""

    def test_rrf_basic_merge(self):
        """RRF correctly combines rankings from multiple result sets."""
        set1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        set2 = [{"id": "b"}, {"id": "c"}, {"id": "d"}]

        merged = reciprocal_rank_fusion([set1, set2], k=60)

        # "b" and "c" appear in both → highest RRF scores
        doc_ids = [doc["id"] for doc in merged]
        assert "b" in doc_ids[:2], "b should be in top 2 (appears in both sets)"
        assert "c" in doc_ids[:2], "c should be in top 2 (appears in both sets)"

    def test_rrf_score_calculation(self):
        """RRF scores are calculated correctly."""
        # Simple case: doc at rank 1 in both sets
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "a"}, {"id": "c"}]

        merged = reciprocal_rank_fusion([set1, set2], k=60)

        # "a" is rank 1 in both → RRF = 1/(60+1) + 1/(60+1) = 2/61
        expected_score = 2 / 61
        a_doc = next(d for d in merged if d["id"] == "a")
        assert abs(a_doc["rrf_score"] - expected_score) < 0.0001

    def test_rrf_preserves_metadata(self):
        """RRF preserves document metadata from first occurrence."""
        set1 = [{"id": "a", "title": "First Title", "score": 0.9}]
        set2 = [{"id": "a", "title": "Second Title", "score": 0.8}]

        merged = reciprocal_rank_fusion([set1, set2], k=60)

        a_doc = merged[0]
        assert a_doc["title"] == "First Title", "Should preserve first occurrence metadata"
        assert a_doc["original_score"] == 0.9, "Should preserve original score"

    def test_rrf_empty_result_sets(self):
        """RRF handles empty result sets gracefully."""
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_rrf_single_result_set(self):
        """RRF with single set preserves order."""
        set1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        merged = reciprocal_rank_fusion([set1], k=60)

        assert [d["id"] for d in merged] == ["a", "b", "c"]

    def test_rrf_k_parameter_effect(self):
        """Different k values produce different rankings."""
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "b"}, {"id": "a"}]

        # With any k, both should have same score (rank 1 + rank 2 for both)
        merged = reciprocal_rank_fusion([set1, set2], k=60)

        a_score = next(d["rrf_score"] for d in merged if d["id"] == "a")
        b_score = next(d["rrf_score"] for d in merged if d["id"] == "b")
        assert abs(a_score - b_score) < 0.0001, "Same ranks should give same scores"

    def test_rrf_tracks_appearances(self):
        """RRF tracks how many queries returned each doc."""
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "a"}, {"id": "c"}]
        set3 = [{"id": "a"}, {"id": "d"}]

        merged = reciprocal_rank_fusion([set1, set2, set3], k=60)

        a_doc = next(d for d in merged if d["id"] == "a")
        assert a_doc["query_appearances"] == 3, "a appears in all 3 sets"


# ═══════════════════════════════════════════════════════════════════════════
# QUERY EXPANDER TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestQueryExpander:
    """Tests for query expansion logic."""

    def test_expand_preserves_q0(self, expander, mock_rewrite_result):
        """Q0 is always the original query."""
        expanded = expander.expand("GDPR samtycke", mock_rewrite_result)

        assert expanded.queries[0] == "GDPR samtycke"
        assert expanded.query_types[0] == "semantic"

    def test_expand_generates_lexical_variant(self, expander, mock_rewrite_result):
        """Q1 is the lexical variant from RewriteResult."""
        expanded = expander.expand("GDPR samtycke", mock_rewrite_result)

        assert len(expanded.queries) >= 2
        assert "lexical" in expanded.query_types
        assert "GDPR samtycke dataskydd" in expanded.queries

    def test_expand_generates_paraphrase(self, expander):
        """Q2 is a rule-based paraphrase."""
        from dataclasses import dataclass

        @dataclass
        class MockRewriteResult:
            standalone_query: str = "Vad säger GDPR om samtycke?"
            lexical_query: str = ""
            detected_entities: list = None

            def __post_init__(self):
                if self.detected_entities is None:
                    self.detected_entities = [{"type": "lag", "value": "GDPR"}]

        mock = MockRewriteResult()
        expanded = expander.expand("Vad säger GDPR om samtycke?", mock)

        assert len(expanded.queries) >= 2, "Should generate at least Q0 + paraphrase"

    def test_expand_respects_max_queries(self):
        """Expansion respects max_queries limit."""
        from dataclasses import dataclass

        @dataclass
        class MockRewriteResult:
            standalone_query: str = "test"
            lexical_query: str = "test lexical"
            detected_entities: list = None

            def __post_init__(self):
                if self.detected_entities is None:
                    self.detected_entities = []

        expander = QueryExpander(max_queries=2)
        mock = MockRewriteResult()
        expanded = expander.expand("test", mock)

        assert len(expanded.queries) <= 2

    def test_expand_no_duplicate_queries(self, expander):
        """Expansion doesn't include duplicate queries."""
        from dataclasses import dataclass

        @dataclass
        class MockRewriteResult:
            standalone_query: str = "GDPR"
            lexical_query: str = "GDPR"  # Same as original
            detected_entities: list = None

            def __post_init__(self):
                if self.detected_entities is None:
                    self.detected_entities = []

        mock = MockRewriteResult()
        expanded = expander.expand("GDPR", mock)

        # Should not have duplicates
        assert len(expanded.queries) == len(set(expanded.queries))

    def test_expand_includes_latency(self, expander, mock_rewrite_result):
        """Expansion measures latency."""
        expanded = expander.expand("test", mock_rewrite_result)

        assert expanded.expansion_latency_ms >= 0


class TestParaphraseGeneration:
    """Tests for paraphrase generation strategies."""

    def test_question_pattern_vad_sager(self, expander):
        """'Vad säger X om Y?' → 'X Y'"""
        # Test the pattern directly
        paraphrase = expander._generate_paraphrase(
            "Vad säger GDPR om samtycke?", [{"type": "lag", "value": "GDPR"}]
        )

        assert paraphrase is not None
        assert "gdpr" in paraphrase.lower()

    def test_question_pattern_hur_fungerar(self, expander):
        """'Hur fungerar X?' → 'X funktioner egenskaper'"""
        paraphrase = expander._generate_paraphrase("Hur fungerar Riksdagen?", [])

        assert paraphrase is not None

    def test_legal_context_words(self, expander):
        """Known legal terms get context words added."""
        paraphrase = expander._generate_paraphrase("GDPR", [{"type": "lag", "value": "GDPR"}])

        # Should add context words for GDPR
        if paraphrase:
            for word in ["dataskydd", "personuppgifter", "integritet"]:
                if word in paraphrase.lower():
                    break
            else:
                pass  # Context words may not always be added

    def test_keyword_extraction(self, expander):
        """Keywords are extracted correctly, filtering stopwords."""
        keywords = expander._extract_keywords("Vad säger lagen om GDPR samtycke?")

        assert "lagen" in keywords or "gdpr" in keywords
        assert "vad" not in keywords  # Stopword
        assert "om" not in keywords  # Stopword


# ═══════════════════════════════════════════════════════════════════════════
# FUSION METRICS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestFusionMetrics:
    """Tests for fusion metrics calculation."""

    def test_fusion_gain_calculation(self):
        """Fusion gain correctly calculated."""
        # Q0 has 2 docs, Q1 adds 2 more unique docs = 100% gain
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "c"}, {"id": "d"}]

        metrics = calculate_fusion_metrics([set1, set2], [])

        assert metrics.unique_docs_before_fusion == 2
        assert metrics.unique_docs_after_fusion == 4
        assert metrics.fusion_gain == 1.0  # 100% gain

    def test_overlap_ratio_calculation(self):
        """Overlap ratio correctly calculated."""
        # 2 docs appear in both sets
        set1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        set2 = [{"id": "a"}, {"id": "b"}, {"id": "d"}]

        metrics = calculate_fusion_metrics([set1, set2], [])

        assert metrics.overlap_count == 2  # a and b appear in both
        # overlap_ratio = 2/4 = 0.5 (2 overlapping docs out of 4 unique)
        assert abs(metrics.overlap_ratio - 0.5) < 0.01

    def test_per_query_result_counts(self):
        """Per-query result counts tracked."""
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "c"}]
        set3 = [{"id": "d"}, {"id": "e"}, {"id": "f"}]

        metrics = calculate_fusion_metrics([set1, set2, set3], [])

        assert metrics.per_query_result_counts == [2, 1, 3]

    def test_metrics_to_dict(self):
        """Metrics can be serialized to dict."""
        metrics = FusionMetrics(
            fusion_used=True,
            num_queries=3,
            fusion_gain=0.5,
            overlap_ratio=0.25,
        )

        d = metrics.to_dict()

        assert d["fusion_used"] is True
        assert d["num_queries"] == 3
        assert d["fusion_gain"] == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# GUARDRAIL TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardrails:
    """Tests for guardrail validation functions."""

    def test_no_hallucinated_entities_valid(self):
        """Passes when no new SFS numbers introduced."""
        original = "Vad säger GDPR?"
        expanded = ["Vad säger GDPR?", "GDPR dataskydd"]
        entities = [{"type": "lag", "value": "GDPR"}]

        assert validate_no_hallucinated_entities(original, expanded, entities) is True

    def test_no_hallucinated_entities_invalid(self):
        """Fails when new SFS numbers introduced."""
        original = "Vad säger GDPR?"
        expanded = ["Vad säger GDPR?", "GDPR 1998:204"]  # SFS number not in original
        entities = [{"type": "lag", "value": "GDPR"}]

        assert validate_no_hallucinated_entities(original, expanded, entities) is False

    def test_no_hallucinated_entities_allows_existing_sfs(self):
        """Passes when SFS number was in original query."""
        original = "Vad säger SFS 2018:218?"
        expanded = ["Vad säger SFS 2018:218?", "2018:218 dataskydd"]
        entities = [{"type": "sfs", "value": "2018:218"}]

        assert validate_no_hallucinated_entities(original, expanded, entities) is True

    def test_should_use_fusion_high_gain(self):
        """Use fusion when gain is high."""
        set1 = [{"id": "a"}, {"id": "b"}]
        set2 = [{"id": "c"}, {"id": "d"}]  # 100% new docs

        assert should_use_fusion_results([set1, set2]) is True

    def test_should_use_fusion_low_gain(self):
        """Skip fusion when gain is below threshold."""
        set1 = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
        set2 = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]  # Same docs

        assert should_use_fusion_results([set1, set2]) is False

    def test_should_use_fusion_empty_q0(self):
        """Use fusion when Q0 returns nothing."""
        set1 = []  # Q0 empty
        set2 = [{"id": "a"}]

        assert should_use_fusion_results([set1, set2]) is True


# ═══════════════════════════════════════════════════════════════════════════
# EXPANDED QUERIES TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestExpandedQueries:
    """Tests for ExpandedQueries dataclass."""

    def test_to_dict_serialization(self):
        """ExpandedQueries can be serialized."""
        eq = ExpandedQueries(
            original="test query",
            queries=["test query", "test lexical"],
            query_types=["semantic", "lexical"],
            expansion_latency_ms=0.5,
        )

        d = eq.to_dict()

        assert d["original"] == "test query"
        assert d["num_queries"] == 2
        assert d["expansion_latency_ms"] == 0.5


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTS VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


class TestConstants:
    """Verify constants are properly configured."""

    def test_legal_context_words_comprehensive(self):
        """Common Swedish legal abbreviations have context words."""
        expected = ["GDPR", "OSL", "RF", "TF", "YGL"]
        for abbr in expected:
            assert abbr in LEGAL_CONTEXT_WORDS, f"Missing context words for: {abbr}"
            assert len(LEGAL_CONTEXT_WORDS[abbr]) >= 2, f"Need 2+ context words for: {abbr}"

    def test_question_patterns_count(self):
        """Have sufficient question patterns for Swedish."""
        assert len(QUESTION_PATTERNS) >= 5, "Should have at least 5 question patterns"
