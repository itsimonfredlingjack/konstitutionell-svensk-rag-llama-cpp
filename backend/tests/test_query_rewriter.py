"""
Unit tests for QueryRewriter — conversational query reformulation
for Swedish constitutional/legal queries.

Tests cover:
- needs_rewrite: pronoun detection, short-query heuristic, explicit entities
- extract_entities: SFS numbers, kapitel, paragraf, lag abbreviations, myndigheter
- decontextualize: pronoun replacement from history, no-history passthrough
- rewrite: full pipeline, latency tracking, RewriteResult fields
- Guardrails: validate_must_include, validate_no_hallucination, validate_sanity
"""

import pytest

from app.services.query_rewriter import (
    QueryRewriter,
    RewriteResult,
    validate_must_include,
    validate_no_hallucination,
    validate_sanity,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def rewriter() -> QueryRewriter:
    return QueryRewriter()


# ═══════════════════════════════════════════════════════════════════
# needs_rewrite
# ═══════════════════════════════════════════════════════════════════


class TestNeedsRewrite:
    def test_pronoun_den_triggers(self, rewriter: QueryRewriter):
        """'den' is a Swedish pronoun → needs rewrite."""
        assert rewriter.needs_rewrite("Vad säger den?") is True

    def test_pronoun_dessa(self, rewriter: QueryRewriter):
        assert rewriter.needs_rewrite("Hur gäller dessa regler?") is True

    def test_pronoun_detta(self, rewriter: QueryRewriter):
        assert rewriter.needs_rewrite("Berätta om detta") is True

    def test_explicit_entity_no_rewrite(self, rewriter: QueryRewriter):
        """A clear entity like GDPR means no pronoun ambiguity."""
        assert rewriter.needs_rewrite("GDPR") is False

    def test_full_query_no_rewrite(self, rewriter: QueryRewriter):
        """No pronoun + explicit entity → no rewrite needed."""
        assert rewriter.needs_rewrite("Vad säger GDPR om samtycke?") is False

    def test_short_query_no_entity_needs_rewrite(self, rewriter: QueryRewriter):
        """Very short queries (<=3 words) without entities need rewrite."""
        assert rewriter.needs_rewrite("Berätta mer") is True

    def test_short_query_with_sfs_no_rewrite(self, rewriter: QueryRewriter):
        """Short query with SFS number is self-contained."""
        assert rewriter.needs_rewrite("1998:204") is False


# ═══════════════════════════════════════════════════════════════════
# extract_entities
# ═══════════════════════════════════════════════════════════════════


class TestExtractEntities:
    def test_sfs_number(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        types = {e["type"] for e in entities}
        assert "sfs" in types

    def test_kapitel(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        types = {e["type"] for e in entities}
        assert "kapitel" in types

    def test_paragraf(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        types = {e["type"] for e in entities}
        assert "paragraf" in types

    def test_sfs_value(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        sfs = [e for e in entities if e["type"] == "sfs"]
        assert sfs[0]["value"] == "1998:204"

    def test_kapitel_value(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        kap = [e for e in entities if e["type"] == "kapitel"]
        assert kap[0]["value"] == "21"

    def test_paragraf_value(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("1998:204 21 kap. 14 §")
        par = [e for e in entities if e["type"] == "paragraf"]
        assert par[0]["value"] == "14"

    def test_gdpr_is_lag(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("GDPR")
        lag = [e for e in entities if e["type"] == "lag"]
        assert len(lag) == 1
        assert lag[0]["value"] == "GDPR"

    def test_skatteverket_is_myndighet(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("Skatteverket")
        myndighet = [e for e in entities if e["type"] == "myndighet"]
        assert len(myndighet) == 1
        assert myndighet[0]["value"] == "Skatteverket"

    def test_empty_text_no_entities(self, rewriter: QueryRewriter):
        assert rewriter.extract_entities("") == []

    def test_no_legal_content(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("hej på dig")
        assert entities == []

    def test_multiple_entities(self, rewriter: QueryRewriter):
        entities = rewriter.extract_entities("GDPR och OSL gäller för Skatteverket")
        types = {e["type"] for e in entities}
        assert "lag" in types
        assert "myndighet" in types
        assert len(entities) >= 3  # GDPR, OSL, Skatteverket


# ═══════════════════════════════════════════════════════════════════
# decontextualize
# ═══════════════════════════════════════════════════════════════════


class TestDecontextualize:
    def test_replaces_pronoun_with_entity(self, rewriter: QueryRewriter):
        """'den' should be replaced by 'GDPR' from history."""
        result = rewriter.decontextualize(
            "Vad säger den om samtycke?",
            history=["Berätta om GDPR"],
        )
        assert "GDPR" in result
        # The pronoun 'den' should be replaced
        assert result != "Vad säger den om samtycke?"

    def test_no_history_returns_original(self, rewriter: QueryRewriter):
        query = "Vad säger den om samtycke?"
        assert rewriter.decontextualize(query, history=None) == query

    def test_empty_history_returns_original(self, rewriter: QueryRewriter):
        query = "Vad säger den om samtycke?"
        assert rewriter.decontextualize(query, history=[]) == query

    def test_no_entities_in_history_returns_original(self, rewriter: QueryRewriter):
        """If history has no extractable entities, query is unchanged."""
        query = "Vad säger den?"
        result = rewriter.decontextualize(query, history=["hej på dig"])
        assert result == query

    def test_priority_lag_over_myndighet(self, rewriter: QueryRewriter):
        """'lag' type entities are prioritized over 'myndighet'."""
        result = rewriter.decontextualize(
            "Vad säger den?",
            history=["Fråga om GDPR och Skatteverket"],
        )
        # GDPR (lag) should be preferred over Skatteverket (myndighet)
        assert "GDPR" in result


# ═══════════════════════════════════════════════════════════════════
# rewrite (full pipeline)
# ═══════════════════════════════════════════════════════════════════


class TestRewrite:
    def test_returns_rewrite_result(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR om samtycke?")
        assert isinstance(result, RewriteResult)

    def test_all_fields_populated(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR om samtycke?")
        assert result.original_query == "Vad säger GDPR om samtycke?"
        assert isinstance(result.standalone_query, str)
        assert isinstance(result.expanded_query, str)
        assert isinstance(result.lexical_query, str)
        assert isinstance(result.must_include, list)
        assert isinstance(result.detected_entities, list)

    def test_latency_positive(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR om samtycke?")
        assert result.rewrite_latency_ms > 0

    def test_needs_rewrite_flag(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger den om samtycke?")
        assert result.needs_rewrite is True

    def test_no_rewrite_flag(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR om samtycke?")
        assert result.needs_rewrite is False

    def test_gdpr_in_must_include(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR om samtycke?")
        assert "GDPR" in result.must_include

    def test_decontextualized_standalone(self, rewriter: QueryRewriter):
        """When history is provided and rewrite needed, standalone differs."""
        result = rewriter.rewrite(
            "Vad säger den om samtycke?",
            history=["Berätta om GDPR"],
        )
        assert "GDPR" in result.standalone_query

    def test_abbreviation_expansion(self, rewriter: QueryRewriter):
        """Legal abbreviations should be expanded in expanded_query."""
        result = rewriter.rewrite("Vad säger TF?")
        # TF should be expanded to include "Tryckfrihetsförordningen"
        assert "Tryckfrihetsförordningen" in result.expanded_query

    def test_to_dict(self, rewriter: QueryRewriter):
        result = rewriter.rewrite("Vad säger GDPR?")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "original_query" in d
        assert "standalone_query" in d
        assert "rewrite_latency_ms" in d


# ═══════════════════════════════════════════════════════════════════
# GUARDRAILS
# ═══════════════════════════════════════════════════════════════════


class TestValidateMustInclude:
    def test_term_present_passes(self):
        result = RewriteResult(
            original_query="GDPR",
            standalone_query="GDPR",
            expanded_query="GDPR",
            lexical_query="GDPR",
            must_include=["GDPR"],
        )
        search_results = [{"snippet": "GDPR handlar om dataskydd"}]
        assert validate_must_include(result, search_results) is True

    def test_term_missing_fails(self):
        result = RewriteResult(
            original_query="GDPR",
            standalone_query="GDPR",
            expanded_query="GDPR",
            lexical_query="GDPR",
            must_include=["GDPR"],
        )
        search_results = [{"snippet": "Inga relevanta resultat"}]
        assert validate_must_include(result, search_results) is False

    def test_empty_must_include_passes(self):
        result = RewriteResult(
            original_query="hej",
            standalone_query="hej",
            expanded_query="hej",
            lexical_query="hej",
            must_include=[],
        )
        assert validate_must_include(result, []) is True

    def test_case_insensitive(self):
        result = RewriteResult(
            original_query="GDPR",
            standalone_query="GDPR",
            expanded_query="GDPR",
            lexical_query="GDPR",
            must_include=["GDPR"],
        )
        search_results = [{"snippet": "gdpr information"}]
        assert validate_must_include(result, search_results) is True


class TestValidateNoHallucination:
    def test_no_new_entities_passes(self):
        """Standalone has same entities as original → pass."""
        assert validate_no_hallucination("Vad säger GDPR?", "Vad säger GDPR?") is True

    def test_hallucinated_entity_fails(self):
        """Standalone introduces an entity not in original or history → fail."""
        assert (
            validate_no_hallucination(
                "Vad säger lagen?",
                "Vad säger 1998:204?",  # Introduces SFS number
            )
            is False
        )

    def test_entity_from_history_ok(self):
        """Entity present in history is allowed."""
        assert (
            validate_no_hallucination(
                "Vad säger den?",
                "Vad säger GDPR?",
                history=["Berätta om GDPR"],
            )
            is True
        )

    def test_no_entities_passes(self):
        """No entities in either → trivially passes."""
        assert validate_no_hallucination("hej", "hej") is True


class TestValidateSanity:
    def test_same_length_passes(self):
        assert validate_sanity("Vad säger lagen?", "Vad säger lagen?") is True

    def test_ratio_within_bounds_passes(self):
        """Length ratio in [0.5, 3.0] → pass."""
        original = "Kort fråga"
        standalone = "Kort fråga om ämnet"  # ~2x length
        assert validate_sanity(original, standalone) is True

    def test_too_short_fails(self):
        """Length ratio < 0.5 → fail."""
        original = "En ganska lång fråga om juridiska ämnen i Sverige"
        standalone = "Kort"
        assert validate_sanity(original, standalone) is False

    def test_too_long_fails(self):
        """Length ratio > 3.0 → fail."""
        original = "X"
        standalone = "En mycket mycket längre fråga"  # way more than 3x
        assert validate_sanity(original, standalone) is False

    def test_empty_original_passes(self):
        """Edge case: empty original → passes (guard clause)."""
        assert validate_sanity("", "anything") is True
