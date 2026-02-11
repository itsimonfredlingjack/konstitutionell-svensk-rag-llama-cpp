"""
Tests for RAG-Fusion service — reciprocal rank fusion, query expansion, and guardrails.

Covers:
- reciprocal_rank_fusion (standard RRF)
- hybrid_reciprocal_rank_fusion (dense + BM25 weighted)
- calculate_fusion_metrics (overlap, gain)
- validate_no_hallucinated_entities
- should_use_fusion_results
- QueryExpander.expand / _generate_paraphrase
"""

import pytest

from app.services.rag_fusion import (
    QueryExpander,
    calculate_fusion_metrics,
    hybrid_reciprocal_rank_fusion,
    reciprocal_rank_fusion,
    should_use_fusion_results,
    validate_no_hallucinated_entities,
)


# ── Helpers ───────────────────────────────────────────────────────


def _doc(doc_id: str, score: float = 0.5) -> dict:
    """Create a minimal document dict for RRF testing."""
    return {"id": doc_id, "score": score, "title": f"Doc {doc_id}"}


def _make_rewrite_result(lexical_query=None, detected_entities=None):
    """Create a mock RewriteResult-like object."""

    class _Fake:
        pass

    r = _Fake()
    r.lexical_query = lexical_query
    r.detected_entities = detected_entities or []
    return r


# ═══════════════════════════════════════════════════════════════════
# reciprocal_rank_fusion
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestReciprocalRankFusion:
    def test_empty_input_returns_empty(self):
        assert reciprocal_rank_fusion([]) == []

    def test_single_result_set_scores(self):
        """Single set: score for each doc = 1/(k+rank)."""
        docs = [_doc("a"), _doc("b")]
        merged = reciprocal_rank_fusion([docs], k=60.0)

        assert len(merged) == 2
        assert merged[0]["id"] == "a"
        assert merged[0]["rrf_score"] == pytest.approx(1.0 / (60 + 1))
        assert merged[1]["rrf_score"] == pytest.approx(1.0 / (60 + 2))

    def test_two_sets_rrf_formula(self):
        """Two sets with k=60: RRF(d) = sum(1/(k+rank_i)) for each set."""
        set1 = [_doc("a"), _doc("b")]
        set2 = [_doc("b"), _doc("c")]
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)

        expected_b = 1.0 / (60 + 2) + 1.0 / (60 + 1)  # rank 2 in set1, rank 1 in set2
        expected_a = 1.0 / (60 + 1)  # only in set1 rank 1
        expected_c = 1.0 / (60 + 2)  # only in set2 rank 2

        scores = {d["id"]: d["rrf_score"] for d in merged}
        assert scores["b"] == pytest.approx(expected_b)
        assert scores["a"] == pytest.approx(expected_a)
        assert scores["c"] == pytest.approx(expected_c)

    def test_overlapping_docs_get_higher_scores(self):
        """Doc appearing in both sets should score higher than any single-set doc."""
        set1 = [_doc("overlap"), _doc("only1")]
        set2 = [_doc("overlap"), _doc("only2")]
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)

        scores = {d["id"]: d["rrf_score"] for d in merged}
        assert scores["overlap"] > scores["only1"]
        assert scores["overlap"] > scores["only2"]

    def test_results_sorted_descending(self):
        """Merged results must be sorted by RRF score descending."""
        set1 = [_doc("a"), _doc("b"), _doc("c")]
        set2 = [_doc("c"), _doc("a")]
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)

        rrf_scores = [d["rrf_score"] for d in merged]
        assert rrf_scores == sorted(rrf_scores, reverse=True)

    def test_docs_without_id_skipped(self):
        """Docs missing 'id' should be silently skipped."""
        docs = [{"score": 0.9}, _doc("valid")]
        merged = reciprocal_rank_fusion([docs], k=60.0)
        assert len(merged) == 1
        assert merged[0]["id"] == "valid"

    def test_query_appearances_tracked(self):
        """Doc appearing in 2 sets should have query_appearances=2."""
        set1 = [_doc("x")]
        set2 = [_doc("x")]
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)
        assert merged[0]["query_appearances"] == 2


# ═══════════════════════════════════════════════════════════════════
# hybrid_reciprocal_rank_fusion
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestHybridRRF:
    def test_bm25_weight_amplifies_contribution(self):
        """BM25 results with weight=1.5 contribute 1.5x per rank."""
        dense = [[_doc("a")]]
        bm25 = [_doc("a")]
        merged = hybrid_reciprocal_rank_fusion(dense, bm25_results=bm25, k=60.0, bm25_weight=1.5)

        expected = 1.0 / (60 + 1) + 1.5 * (1.0 / (60 + 1))
        assert merged[0]["rrf_score"] == pytest.approx(expected)

    def test_only_bm25_no_dense(self):
        """No dense sets, only BM25 → returns BM25 docs with RRF scores."""
        bm25 = [_doc("b1"), _doc("b2")]
        merged = hybrid_reciprocal_rank_fusion([], bm25_results=bm25, k=60.0)

        assert len(merged) == 2
        # rank is 0-indexed in bm25-only path: score = 1/(k + rank + 1)
        assert merged[0]["rrf_score"] == pytest.approx(1.0 / (60 + 0 + 1))
        assert merged[1]["rrf_score"] == pytest.approx(1.0 / (60 + 1 + 1))

    def test_no_bm25_same_as_regular_rrf(self):
        """No BM25 results → should behave like plain RRF."""
        dense_sets = [[_doc("a"), _doc("b")], [_doc("b"), _doc("c")]]
        hybrid = hybrid_reciprocal_rank_fusion(dense_sets, bm25_results=None, k=60.0)
        regular = reciprocal_rank_fusion(dense_sets, k=60.0)

        # Scores should match (hybrid adds retriever_sources/found_by_bm25 extra keys)
        hybrid_scores = {d["id"]: d["rrf_score"] for d in hybrid}
        regular_scores = {d["id"]: d["rrf_score"] for d in regular}
        for doc_id in regular_scores:
            assert hybrid_scores[doc_id] == pytest.approx(regular_scores[doc_id])

    def test_empty_dense_empty_bm25_returns_empty(self):
        merged = hybrid_reciprocal_rank_fusion([], bm25_results=None, k=60.0)
        assert merged == []

    def test_found_by_bm25_flag(self):
        """Documents found by BM25 should have found_by_bm25=True."""
        dense = [[_doc("a")]]
        bm25 = [_doc("b")]
        merged = hybrid_reciprocal_rank_fusion(dense, bm25_results=bm25, k=60.0)

        docs = {d["id"]: d for d in merged}
        assert docs["b"]["found_by_bm25"] is True
        assert docs["a"]["found_by_bm25"] is False


# ═══════════════════════════════════════════════════════════════════
# calculate_fusion_metrics
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFusionMetrics:
    def test_empty_result_sets(self):
        metrics = calculate_fusion_metrics([], [])
        assert metrics.fusion_used is False

    def test_overlap_count_correct(self):
        """Doc appearing in 2+ sets counted as overlapping."""
        set1 = [_doc("a"), _doc("b")]
        set2 = [_doc("b"), _doc("c")]
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)
        metrics = calculate_fusion_metrics([set1, set2], merged)

        assert metrics.overlap_count == 1  # "b" in both sets

    def test_fusion_gain_calculated(self):
        """fusion_gain = (after - before) / before."""
        set1 = [_doc("a"), _doc("b")]  # 2 unique in Q0
        set2 = [_doc("c")]  # 1 new doc
        merged = reciprocal_rank_fusion([set1, set2], k=60.0)
        metrics = calculate_fusion_metrics([set1, set2], merged)

        assert metrics.unique_docs_before_fusion == 2
        assert metrics.unique_docs_after_fusion == 3
        assert metrics.fusion_gain == pytest.approx(0.5)  # (3-2)/2

    def test_single_result_set_no_overlap(self):
        """Single result set → overlap=0, gain=0."""
        set1 = [_doc("a"), _doc("b")]
        merged = reciprocal_rank_fusion([set1], k=60.0)
        metrics = calculate_fusion_metrics([set1], merged)

        assert metrics.overlap_count == 0
        assert metrics.fusion_gain == pytest.approx(0.0)

    def test_expanded_queries_metadata(self):
        """When ExpandedQueries is provided, metrics include query_variants."""
        from app.services.rag_fusion import ExpandedQueries

        eq = ExpandedQueries(
            original="test",
            queries=["test", "test2"],
            query_types=["semantic", "lexical"],
            expansion_latency_ms=1.5,
        )
        set1 = [_doc("a")]
        metrics = calculate_fusion_metrics([set1], [_doc("a")], expanded_queries=eq)

        assert metrics.query_variants == ["test", "test2"]
        assert metrics.expansion_latency_ms == pytest.approx(1.5)


# ═══════════════════════════════════════════════════════════════════
# Guardrails
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFusionGuardrails:
    def test_validate_no_hallucinated_entities_clean(self):
        """Same SFS numbers in original and expanded → True."""
        original = "Vad säger 2018:218 om personuppgifter?"
        expanded = [original, "dataskyddslagen 2018:218"]
        entities = [{"type": "sfs", "value": "2018:218"}]

        assert validate_no_hallucinated_entities(original, expanded, entities) is True

    def test_validate_hallucinated_sfs_blocked(self):
        """New SFS number in expanded query → False."""
        original = "Vad säger lagen?"
        expanded = [original, "SFS 1999:123 dataskydd"]
        entities = []

        assert validate_no_hallucinated_entities(original, expanded, entities) is False

    def test_should_use_fusion_below_threshold(self):
        """Gain below 5% → False."""
        # Both sets have the same docs → gain = 0%
        set1 = [_doc("a"), _doc("b")]
        set2 = [_doc("a"), _doc("b")]
        assert should_use_fusion_results([set1, set2], min_gain_threshold=0.05) is False

    def test_should_use_fusion_above_threshold(self):
        """Gain above 5% → True."""
        set1 = [_doc("a")]
        set2 = [_doc("b")]  # 100% gain (1→2)
        assert should_use_fusion_results([set1, set2], min_gain_threshold=0.05) is True

    def test_should_use_fusion_single_set(self):
        """Less than 2 sets → False."""
        assert should_use_fusion_results([[_doc("a")]], min_gain_threshold=0.05) is False

    def test_should_use_fusion_empty(self):
        assert should_use_fusion_results([], min_gain_threshold=0.05) is False


# ═══════════════════════════════════════════════════════════════════
# QueryExpander
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestQueryExpander:
    def test_expand_generates_up_to_max_queries(self):
        """Should not exceed max_queries variants."""
        expander = QueryExpander(max_queries=2)
        rewrite = _make_rewrite_result(lexical_query="GDPR dataskydd", detected_entities=[])
        result = expander.expand("Vad säger GDPR om dataskydd?", rewrite)

        assert len(result.queries) <= 2
        assert result.queries[0] == "Vad säger GDPR om dataskydd?"

    def test_expand_includes_lexical_query(self):
        """Q1 should be the lexical_query from RewriteResult."""
        expander = QueryExpander(max_queries=3)
        rewrite = _make_rewrite_result(lexical_query="personuppgifter GDPR")
        result = expander.expand("Vad gäller för personuppgifter?", rewrite)

        assert "personuppgifter GDPR" in result.queries
        assert "lexical" in result.query_types

    def test_expand_no_duplicate_queries(self):
        """Lexical query identical to original should not be added."""
        query = "GDPR dataskydd"
        expander = QueryExpander(max_queries=3)
        rewrite = _make_rewrite_result(lexical_query="GDPR dataskydd")
        result = expander.expand(query, rewrite)

        assert result.queries.count(query) == 1

    def test_paraphrase_vad_sager_pattern(self):
        """'Vad säger X om Y?' → 'X Y'."""
        expander = QueryExpander(max_queries=3)
        rewrite = _make_rewrite_result()
        result = expander.expand("Vad säger GDPR om dataskydd?", rewrite)

        # Q2 paraphrase should exist
        if len(result.queries) >= 2:
            assert any("paraphrase" in t for t in result.query_types)

    def test_paraphrase_vad_ar_pattern(self):
        """'Vad är X?' → 'X definition betydelse'."""
        expander = QueryExpander(max_queries=3)
        paraphrase = expander._generate_paraphrase("vad är offentlighetsprincipen?", [])
        assert paraphrase is not None
        assert "offentlighetsprincipen" in paraphrase
        assert "definition" in paraphrase

    def test_paraphrase_hur_fungerar_pattern(self):
        """'Hur fungerar X?' → 'X funktioner egenskaper'."""
        expander = QueryExpander(max_queries=3)
        paraphrase = expander._generate_paraphrase("hur fungerar riksdagen?", [])
        assert paraphrase is not None
        assert "riksdagen" in paraphrase
        assert "funktioner" in paraphrase

    def test_expand_latency_recorded(self):
        """expansion_latency_ms should be >= 0."""
        expander = QueryExpander(max_queries=3)
        rewrite = _make_rewrite_result()
        result = expander.expand("test query", rewrite)
        assert result.expansion_latency_ms >= 0

    def test_expand_query_types_match_queries(self):
        """len(query_types) == len(queries) always."""
        expander = QueryExpander(max_queries=3)
        rewrite = _make_rewrite_result(lexical_query="legal terms")
        result = expander.expand("What about legal terms?", rewrite)
        assert len(result.queries) == len(result.query_types)
