"""
Tests for Intent Classifier with new EPR intents.

Tests the new intent types:
- PARLIAMENT_TRACE: Parliament process/treatment queries
- POLICY_ARGUMENTS: Political argument queries
- RESEARCH_SYNTHESIS: Research/evidence queries
"""

import pytest

from backend.app.services.intent_classifier import IntentClassifier, QueryIntent


class TestNewIntents:
    """Test the new EPR intent types."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier()

    def test_parliament_trace_detection(self, classifier):
        """PARLIAMENT_TRACE should match parliamentary process queries."""
        queries = [
            "Hur har riksdagen behandlat klimatfrågan?",
            "Vilket utskott hanterade propositionen?",
            "Hur röstade partierna i voteringen?",
            "Vad sa betänkandet om detta?",
            "Hur behandlades förslaget i riksdagen?",
            "Vilket riksdagsbeslut fattades?",
            "Vilken proposition gällande migration?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.PARLIAMENT_TRACE, f"Failed for: {q}"

    def test_policy_arguments_detection(self, classifier):
        """POLICY_ARGUMENTS should match political argument queries."""
        queries = [
            "Vilka argument använde Socialdemokraterna?",
            "Vad var oppositionens kritik mot förslaget?",
            "Vilka partier var för förslaget?",
            "Vad sade regeringen om reformen?",
            "Vilka partier motsatte sig detta?",
            "Kritiken mot förslaget?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.POLICY_ARGUMENTS, f"Failed for: {q}"

    def test_research_synthesis_detection(self, classifier):
        """RESEARCH_SYNTHESIS should match research/evidence queries."""
        queries = [
            "Vad säger forskningen om klimatförändringar?",
            "Vilken evidens finns för detta?",
            "Vad visar studier om effekterna?",
            "Vad är forskningsläget?",
            "Finns det vetenskapligt stöd för detta?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.RESEARCH_SYNTHESIS, f"Failed for: {q}"

    def test_legal_text_still_works(self, classifier):
        """LEGAL_TEXT (formerly SFS_PRIMARY) should still work."""
        result = classifier.classify("Vad säger RF 2:1 om yttrandefrihet?")
        # Should be edge abbreviation since it has RF 2:1
        # Let's test a pure legal text query
        result = classifier.classify("Vilka grundläggande rättigheter finns?")
        assert result.intent == QueryIntent.LEGAL_TEXT, f"Got: {result.intent}"

    def test_practical_process_still_works(self, classifier):
        """PRACTICAL_PROCESS (formerly PRAXIS) should still work."""
        result = classifier.classify("Hur överklagar jag ett myndighetsbeslut?")
        assert result.intent == QueryIntent.PRACTICAL_PROCESS, f"Got: {result.intent}"

    def test_backward_compat_aliases(self, classifier):
        """SFS_PRIMARY and PRAXIS should equal new names."""
        assert QueryIntent.SFS_PRIMARY == QueryIntent.LEGAL_TEXT
        assert QueryIntent.PRAXIS == QueryIntent.PRACTICAL_PROCESS


class TestExistingIntents:
    """Verify existing intents still work correctly."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier()

    def test_smalltalk_detection(self, classifier):
        """SMALLTALK should still work."""
        queries = [
            "Hej!",
            "God morgon!",
            "Hur mår du?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.SMALLTALK, f"Failed for: {q}"

    def test_edge_abbreviation_detection(self, classifier):
        """EDGE_ABBREVIATION should still work."""
        queries = [
            "RF 2:1",
            "Vad står i OSL 21:7?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.EDGE_ABBREVIATION, f"Failed for: {q}"

    def test_edge_clarification_detection(self, classifier):
        """EDGE_CLARIFICATION should still work."""
        queries = [
            "Menar du förvaltningslagen?",
            "Skillnaden mellan RF och TF?",
        ]
        for q in queries:
            result = classifier.classify(q)
            assert result.intent == QueryIntent.EDGE_CLARIFICATION, f"Failed for: {q}"


class TestIntentPriority:
    """Test that intent priority order is correct."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier()

    def test_parliament_beats_legal_text(self, classifier):
        """Parliament-specific query should not fall through to legal text."""
        # "Hur har riksdagen behandlat" is clearly about parliament process
        result = classifier.classify("Hur har riksdagen behandlat lagen om?")
        assert result.intent == QueryIntent.PARLIAMENT_TRACE

    def test_policy_args_beats_legal_text(self, classifier):
        """Policy argument query should be detected."""
        result = classifier.classify("Vilka argument använde partierna om lagen?")
        assert result.intent == QueryIntent.POLICY_ARGUMENTS

    def test_research_beats_legal_text(self, classifier):
        """Research query should be detected."""
        result = classifier.classify("Vad säger forskningen om effekterna?")
        assert result.intent == QueryIntent.RESEARCH_SYNTHESIS


class TestIntentCollections:
    """Test that new intents have proper collection mappings."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier()

    def test_parliament_trace_collections(self, classifier):
        """PARLIAMENT_TRACE should have riksdag collections."""
        collections = classifier.get_collections_for_intent(QueryIntent.PARLIAMENT_TRACE)
        assert any("riksdag" in c for c in collections), f"Got: {collections}"

    def test_policy_arguments_collections(self, classifier):
        """POLICY_ARGUMENTS should have riksdag collections."""
        collections = classifier.get_collections_for_intent(QueryIntent.POLICY_ARGUMENTS)
        assert any("riksdag" in c for c in collections), f"Got: {collections}"

    def test_research_synthesis_collections(self, classifier):
        """RESEARCH_SYNTHESIS should have gov_docs collections."""
        collections = classifier.get_collections_for_intent(QueryIntent.RESEARCH_SYNTHESIS)
        assert any("gov" in c or "sou" in c.lower() for c in collections), f"Got: {collections}"


class TestConfidenceScores:
    """Test that confidence scores are reasonable."""

    @pytest.fixture
    def classifier(self):
        return IntentClassifier()

    def test_strong_pattern_has_high_confidence(self, classifier):
        """Clear pattern match should have high confidence."""
        result = classifier.classify("Hur har riksdagen behandlat klimatfrågan?")
        assert result.confidence >= 0.7, f"Low confidence: {result.confidence}"

    def test_unknown_has_low_confidence(self, classifier):
        """Unmatched query should have low confidence."""
        result = classifier.classify("xyzzy gibberish query")
        assert result.confidence <= 0.5, f"High confidence for unknown: {result.confidence}"
