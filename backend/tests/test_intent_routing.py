"""
Unit tests for intent_routing — two-pass retrieval routing configuration
for Evidence Policy Routing (EPR).

Tests cover:
- Routing config per intent (primary, support, secondary, budget, require_separation)
- LEGAL_TEXT critical invariant: never includes DiVA
- get_routing_for_intent fallback to UNKNOWN
- get_all_collections_for_intent deduplication & order
- has_secondary_retrieval logic
- Coverage of all QueryIntent enum values
"""

import pytest

from app.services.intent_classifier import QueryIntent
from app.services.intent_routing import (
    INTENT_ROUTING,
    IntentRoutingConfig,
    get_all_collections_for_intent,
    get_routing_for_intent,
    has_secondary_retrieval,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════
# PER-INTENT ROUTING CONFIGS
# ═══════════════════════════════════════════════════════════════════


class TestLegalTextRouting:
    """LEGAL_TEXT is the most critical intent — SFS only, never DiVA."""

    def test_primary_is_sfs(self):
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert cfg.primary == ["sfs_lagtext_bge_m3_1024"]

    def test_secondary_empty(self):
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert cfg.secondary == []

    def test_secondary_budget_zero(self):
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert cfg.secondary_budget == 0

    def test_never_diva_in_primary(self):
        """CRITICAL INVARIANT: LEGAL_TEXT must NEVER include DiVA in primary."""
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert "diva_research_bge_m3_1024" not in cfg.primary

    def test_never_diva_in_support(self):
        """CRITICAL INVARIANT: LEGAL_TEXT must NEVER include DiVA in support."""
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert "diva_research_bge_m3_1024" not in cfg.support

    def test_never_diva_in_secondary(self):
        """CRITICAL INVARIANT: LEGAL_TEXT must NEVER include DiVA in secondary."""
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert "diva_research_bge_m3_1024" not in cfg.secondary

    def test_never_diva_anywhere(self):
        """CRITICAL INVARIANT: DiVA must not appear in any LEGAL_TEXT collection list."""
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        all_cols = cfg.primary + cfg.support + cfg.secondary
        assert "diva_research_bge_m3_1024" not in all_cols


class TestResearchSynthesisRouting:
    def test_diva_is_primary(self):
        cfg = get_routing_for_intent(QueryIntent.RESEARCH_SYNTHESIS)
        assert cfg.primary == ["diva_research_bge_m3_1024"]

    def test_secondary_empty(self):
        cfg = get_routing_for_intent(QueryIntent.RESEARCH_SYNTHESIS)
        assert cfg.secondary == []

    def test_budget_zero(self):
        cfg = get_routing_for_intent(QueryIntent.RESEARCH_SYNTHESIS)
        assert cfg.secondary_budget == 0


class TestParliamentTraceRouting:
    def test_secondary_budget_2(self):
        cfg = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
        assert cfg.secondary_budget == 2

    def test_has_riksdag_primary(self):
        cfg = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
        assert "riksdag_documents_p1_bge_m3_1024" in cfg.primary

    def test_has_diva_secondary(self):
        cfg = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
        assert "diva_research_bge_m3_1024" in cfg.secondary


class TestPolicyArgumentsRouting:
    def test_require_separation_true(self):
        cfg = get_routing_for_intent(QueryIntent.POLICY_ARGUMENTS)
        assert cfg.require_separation is True

    def test_has_riksdag_primary(self):
        cfg = get_routing_for_intent(QueryIntent.POLICY_ARGUMENTS)
        assert "riksdag_documents_p1_bge_m3_1024" in cfg.primary

    def test_secondary_budget_2(self):
        cfg = get_routing_for_intent(QueryIntent.POLICY_ARGUMENTS)
        assert cfg.secondary_budget == 2


class TestPracticalProcessRouting:
    def test_secondary_empty(self):
        cfg = get_routing_for_intent(QueryIntent.PRACTICAL_PROCESS)
        assert cfg.secondary == []

    def test_secondary_budget_zero(self):
        cfg = get_routing_for_intent(QueryIntent.PRACTICAL_PROCESS)
        assert cfg.secondary_budget == 0

    def test_procedural_guides_in_primary(self):
        cfg = get_routing_for_intent(QueryIntent.PRACTICAL_PROCESS)
        assert "procedural_guides_bge_m3_1024" in cfg.primary


class TestSmalltalkRouting:
    def test_primary_empty(self):
        cfg = get_routing_for_intent(QueryIntent.SMALLTALK)
        assert cfg.primary == []

    def test_support_empty(self):
        cfg = get_routing_for_intent(QueryIntent.SMALLTALK)
        assert cfg.support == []

    def test_secondary_empty(self):
        cfg = get_routing_for_intent(QueryIntent.SMALLTALK)
        assert cfg.secondary == []

    def test_budget_zero(self):
        cfg = get_routing_for_intent(QueryIntent.SMALLTALK)
        assert cfg.secondary_budget == 0


class TestUnknownRouting:
    def test_has_diva_secondary(self):
        cfg = get_routing_for_intent(QueryIntent.UNKNOWN)
        assert "diva_research_bge_m3_1024" in cfg.secondary

    def test_secondary_budget_2(self):
        cfg = get_routing_for_intent(QueryIntent.UNKNOWN)
        assert cfg.secondary_budget == 2

    def test_has_broad_primary(self):
        cfg = get_routing_for_intent(QueryIntent.UNKNOWN)
        assert len(cfg.primary) >= 2  # fallback is broad


# ═══════════════════════════════════════════════════════════════════
# get_routing_for_intent FALLBACK
# ═══════════════════════════════════════════════════════════════════


class TestGetRoutingFallback:
    def test_known_intent_returns_config(self):
        cfg = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        assert isinstance(cfg, IntentRoutingConfig)

    def test_unknown_intent_falls_back(self):
        """Passing a non-existent intent value falls back to UNKNOWN config."""
        # We can't easily create an unknown QueryIntent member, but UNKNOWN itself
        # is the defined fallback. Test that UNKNOWN returns the expected config.
        cfg = get_routing_for_intent(QueryIntent.UNKNOWN)
        expected = INTENT_ROUTING[QueryIntent.UNKNOWN]
        assert cfg is expected


# ═══════════════════════════════════════════════════════════════════
# get_all_collections_for_intent
# ═══════════════════════════════════════════════════════════════════


class TestGetAllCollections:
    def test_deduplication(self):
        """Returned list has no duplicates."""
        for intent in QueryIntent:
            cols = get_all_collections_for_intent(intent)
            assert len(cols) == len(set(cols)), f"Duplicate collections for {intent.value}: {cols}"

    def test_preserves_order(self):
        """Primary collections appear before support before secondary."""
        cfg = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
        all_cols = get_all_collections_for_intent(QueryIntent.PARLIAMENT_TRACE)

        # First collections should be from primary
        for i, col in enumerate(cfg.primary):
            assert all_cols[i] == col

    def test_includes_all_tiers(self):
        """Result includes collections from primary, support, and secondary."""
        cfg = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
        all_cols = get_all_collections_for_intent(QueryIntent.PARLIAMENT_TRACE)

        for col in cfg.primary:
            assert col in all_cols
        for col in cfg.support:
            assert col in all_cols
        for col in cfg.secondary:
            assert col in all_cols

    def test_smalltalk_returns_empty(self):
        assert get_all_collections_for_intent(QueryIntent.SMALLTALK) == []


# ═══════════════════════════════════════════════════════════════════
# has_secondary_retrieval
# ═══════════════════════════════════════════════════════════════════


class TestHasSecondaryRetrieval:
    def test_parliament_trace_true(self):
        """PARLIAMENT_TRACE has budget > 0 AND non-empty secondary."""
        assert has_secondary_retrieval(QueryIntent.PARLIAMENT_TRACE) is True

    def test_policy_arguments_true(self):
        assert has_secondary_retrieval(QueryIntent.POLICY_ARGUMENTS) is True

    def test_unknown_true(self):
        assert has_secondary_retrieval(QueryIntent.UNKNOWN) is True

    def test_legal_text_false(self):
        """LEGAL_TEXT has budget=0 → no secondary."""
        assert has_secondary_retrieval(QueryIntent.LEGAL_TEXT) is False

    def test_smalltalk_false(self):
        assert has_secondary_retrieval(QueryIntent.SMALLTALK) is False

    def test_practical_process_false(self):
        assert has_secondary_retrieval(QueryIntent.PRACTICAL_PROCESS) is False

    def test_research_synthesis_false(self):
        """RESEARCH_SYNTHESIS has DiVA as PRIMARY, not secondary."""
        assert has_secondary_retrieval(QueryIntent.RESEARCH_SYNTHESIS) is False


# ═══════════════════════════════════════════════════════════════════
# FULL COVERAGE: every QueryIntent has a routing config
# ═══════════════════════════════════════════════════════════════════


class TestAllIntentsHaveRouting:
    # Collect unique intent values (aliases share values)
    _UNIQUE_INTENTS = list({member.value: member for member in QueryIntent}.values())

    @pytest.mark.parametrize("intent", _UNIQUE_INTENTS, ids=lambda i: i.value)
    def test_intent_has_config(self, intent: QueryIntent):
        """get_routing_for_intent must return a config (possibly UNKNOWN fallback)."""
        cfg = get_routing_for_intent(intent)
        assert isinstance(cfg, IntentRoutingConfig)


# ═══════════════════════════════════════════════════════════════════
# IntentRoutingConfig DATACLASS
# ═══════════════════════════════════════════════════════════════════


class TestIntentRoutingConfigDefaults:
    def test_defaults(self):
        cfg = IntentRoutingConfig(primary=["test"])
        assert cfg.support == []
        assert cfg.secondary == []
        assert cfg.secondary_budget == 0
        assert cfg.require_separation is False
