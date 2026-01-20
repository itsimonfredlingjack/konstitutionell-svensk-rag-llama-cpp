"""
Tests for Intent Routing Configuration.

Task 3 of Evidence Policy Routing (EPR) plan.
Tests the two-pass retrieval routing with primary/secondary collections and DiVA budget.
"""

import pytest

from backend.app.services.intent_classifier import QueryIntent
from backend.app.services.intent_routing import IntentRoutingConfig, get_routing_for_intent


def test_parliament_trace_routing():
    config = get_routing_for_intent(QueryIntent.PARLIAMENT_TRACE)
    assert "riksdag_documents_p1_bge_m3_1024" in config.primary
    assert "swedish_gov_docs_bge_m3_1024" in config.primary
    assert config.secondary_budget == 0


def test_policy_arguments_routing():
    config = get_routing_for_intent(QueryIntent.POLICY_ARGUMENTS)
    assert "diva_research_bge_m3_1024" in config.secondary
    assert config.secondary_budget == 2
    assert config.require_separation is True


def test_research_synthesis_routing():
    config = get_routing_for_intent(QueryIntent.RESEARCH_SYNTHESIS)
    assert "diva_research_bge_m3_1024" in config.primary
    assert config.secondary_budget == 0


def test_legal_text_routing():
    config = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
    assert "sfs_lagtext_bge_m3_1024" in config.primary
    assert "diva_research_bge_m3_1024" not in config.primary
    assert "diva_research_bge_m3_1024" not in config.secondary


def test_practical_process_routing():
    config = get_routing_for_intent(QueryIntent.PRACTICAL_PROCESS)
    assert "procedural_guides_bge_m3_1024" in config.primary
    assert "sfs_lagtext_bge_m3_1024" in config.primary


def test_unknown_uses_all_primary():
    config = get_routing_for_intent(QueryIntent.UNKNOWN)
    assert len(config.primary) == 3
    assert config.secondary_budget == 0


def test_smalltalk_has_empty_primary():
    config = get_routing_for_intent(QueryIntent.SMALLTALK)
    assert config.primary == []


class TestIntentRoutingConfig:
    """Test IntentRoutingConfig dataclass structure."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = IntentRoutingConfig(primary=["test_collection"])
        assert config.support == []
        assert config.secondary == []
        assert config.secondary_budget == 0
        assert config.require_separation is False

    def test_full_config(self):
        """Test config with all fields specified."""
        config = IntentRoutingConfig(
            primary=["primary_col"],
            support=["support_col"],
            secondary=["secondary_col"],
            secondary_budget=3,
            require_separation=True,
        )
        assert config.primary == ["primary_col"]
        assert config.support == ["support_col"]
        assert config.secondary == ["secondary_col"]
        assert config.secondary_budget == 3
        assert config.require_separation is True


class TestEdgeCases:
    """Test edge case intents."""

    def test_edge_abbreviation_same_as_legal_text(self):
        """EDGE_ABBREVIATION should route same as LEGAL_TEXT."""
        legal_config = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        edge_config = get_routing_for_intent(QueryIntent.EDGE_ABBREVIATION)
        assert edge_config.primary == legal_config.primary
        assert edge_config.secondary_budget == legal_config.secondary_budget

    def test_edge_clarification_same_as_legal_text(self):
        """EDGE_CLARIFICATION should route same as LEGAL_TEXT."""
        legal_config = get_routing_for_intent(QueryIntent.LEGAL_TEXT)
        edge_config = get_routing_for_intent(QueryIntent.EDGE_CLARIFICATION)
        assert edge_config.primary == legal_config.primary
        assert edge_config.secondary_budget == legal_config.secondary_budget


class TestAllIntentsHaveRouting:
    """Ensure all intents have routing configurations."""

    @pytest.mark.parametrize(
        "intent",
        [
            QueryIntent.LEGAL_TEXT,
            QueryIntent.PARLIAMENT_TRACE,
            QueryIntent.POLICY_ARGUMENTS,
            QueryIntent.RESEARCH_SYNTHESIS,
            QueryIntent.PRACTICAL_PROCESS,
            QueryIntent.EDGE_ABBREVIATION,
            QueryIntent.EDGE_CLARIFICATION,
            QueryIntent.SMALLTALK,
            QueryIntent.UNKNOWN,
        ],
    )
    def test_intent_has_routing(self, intent):
        """Each intent should have a valid routing config."""
        config = get_routing_for_intent(intent)
        assert isinstance(config, IntentRoutingConfig)
        # primary should be a list (can be empty for SMALLTALK)
        assert isinstance(config.primary, list)
        assert isinstance(config.secondary_budget, int)
        assert config.secondary_budget >= 0
