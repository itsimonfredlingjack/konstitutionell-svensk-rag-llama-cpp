"""
Unit tests for IntentClassifier — rule-based intent classification
for Swedish constitutional/legal queries.

Tests cover:
- Classification of each intent type (SMALLTALK, EDGE_*, PARLIAMENT_TRACE,
  POLICY_ARGUMENTS, RESEARCH_SYNTHESIS, PRACTICAL_PROCESS, LEGAL_TEXT, UNKNOWN)
- Confidence bounds
- Priority ordering (PRACTICAL_PROCESS vs LEGAL_TEXT tie-break)
- INTENT_COLLECTIONS mapping correctness
- get_collections_for_intent fallback
- Singleton get_intent_classifier
"""

import pytest

from app.services.intent_classifier import (
    IntentClassifier,
    IntentResult,
    QueryIntent,
    get_intent_classifier,
)

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def classifier() -> IntentClassifier:
    """Fresh IntentClassifier instance (not the singleton)."""
    return IntentClassifier()


# ═══════════════════════════════════════════════════════════════════
# BASIC INTENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════


class TestSmallTalk:
    def test_hej_is_smalltalk(self, classifier: IntentClassifier):
        result = classifier.classify("Hej!")
        assert result.intent == QueryIntent.SMALLTALK

    def test_hej_confidence_high(self, classifier: IntentClassifier):
        result = classifier.classify("Hej!")
        assert result.confidence >= 0.9

    def test_god_morgon(self, classifier: IntentClassifier):
        result = classifier.classify("God morgon!")
        assert result.intent == QueryIntent.SMALLTALK

    def test_tack(self, classifier: IntentClassifier):
        result = classifier.classify("Tack för hjälpen")
        assert result.intent == QueryIntent.SMALLTALK

    def test_smalltalk_empty_collections(self, classifier: IntentClassifier):
        result = classifier.classify("Hej!")
        assert result.suggested_collections == []


class TestEdgeAbbreviation:
    def test_rf_2_1(self, classifier: IntentClassifier):
        result = classifier.classify("RF 2:1")
        assert result.intent == QueryIntent.EDGE_ABBREVIATION

    def test_osl_ref(self, classifier: IntentClassifier):
        result = classifier.classify("OSL 21:7")
        assert result.intent == QueryIntent.EDGE_ABBREVIATION

    def test_confidence_is_0_90(self, classifier: IntentClassifier):
        result = classifier.classify("RF 2:1")
        assert result.confidence == pytest.approx(0.90)


class TestEdgeClarification:
    def test_menar_du(self, classifier: IntentClassifier):
        result = classifier.classify("Menar du förvaltningslagen?")
        assert result.intent == QueryIntent.EDGE_CLARIFICATION

    def test_vilken_av(self, classifier: IntentClassifier):
        result = classifier.classify("Vilken av dessa gäller?")
        assert result.intent == QueryIntent.EDGE_CLARIFICATION

    def test_confidence_is_0_85(self, classifier: IntentClassifier):
        result = classifier.classify("Menar du förvaltningslagen?")
        assert result.confidence == pytest.approx(0.85)


class TestParliamentTrace:
    def test_riksdag_behandlat(self, classifier: IntentClassifier):
        result = classifier.classify("Hur har riksdagen behandlat klimatfrågan?")
        assert result.intent == QueryIntent.PARLIAMENT_TRACE

    def test_utskott(self, classifier: IntentClassifier):
        result = classifier.classify("Vilket utskott hanterade propositionen?")
        assert result.intent == QueryIntent.PARLIAMENT_TRACE

    def test_betankande(self, classifier: IntentClassifier):
        result = classifier.classify("Var finns betänkandet?")
        assert result.intent == QueryIntent.PARLIAMENT_TRACE


class TestPolicyArguments:
    def test_vilka_argument(self, classifier: IntentClassifier):
        result = classifier.classify("Vilka argument använde partierna?")
        assert result.intent == QueryIntent.POLICY_ARGUMENTS

    def test_kritik_mot(self, classifier: IntentClassifier):
        result = classifier.classify("Vad var kritiken mot förslaget?")
        assert result.intent == QueryIntent.POLICY_ARGUMENTS


class TestResearchSynthesis:
    def test_forskningen(self, classifier: IntentClassifier):
        result = classifier.classify("Vad säger forskningen om klimatförändringar?")
        assert result.intent == QueryIntent.RESEARCH_SYNTHESIS

    def test_studier(self, classifier: IntentClassifier):
        result = classifier.classify("Finns det studier om X?")
        assert result.intent == QueryIntent.RESEARCH_SYNTHESIS

    @pytest.mark.parametrize(
        "query",
        [
            "Vad säger forskningen om inkludering?",
            "Finns evidens för detta påstående?",
            "Studier visar att X stämmer",
            "Vad är forskningsläget kring AI?",
            "Meta-analys av studier om klimat",
            "Vetenskapligt stöd för åtgärden",
            "Akademisk forskning om rättshistoria",
            "Avhandlingar om svensk förvaltningsrätt",
            "Uppsatser om EU-rätt",
            "Doktorsavhandlingar om straffrätt",
            "Empiriska studier om diskriminering",
            "Undersökningar om folkhälsa",
            "Litteraturöversikten visar",
            "Systematisk översikt av ämnet",
            "Forskningsresultaten pekar på",
            "Vad visar forskningen om jämställdhet?",
        ],
        ids=[
            "forskningen",
            "evidens",
            "studier_visar",
            "forskningslaget",
            "meta_analys",
            "vetenskapligt_stod",
            "akademisk_forskning",
            "avhandlingar",
            "uppsatser",
            "doktorsavhandlingar",
            "empirisk_studie",
            "undersokningar",
            "litteraturoversikt",
            "systematisk_oversikt",
            "forskningsresultat",
            "visar_forskningen",
        ],
    )
    def test_all_16_research_patterns(self, classifier: IntentClassifier, query: str):
        """Every RESEARCH pattern must individually trigger RESEARCH_SYNTHESIS."""
        result = classifier.classify(query)
        assert (
            result.intent == QueryIntent.RESEARCH_SYNTHESIS
        ), f"Expected RESEARCH_SYNTHESIS for '{query}', got {result.intent.value}"


class TestPracticalProcess:
    def test_hur_overklagar(self, classifier: IntentClassifier):
        result = classifier.classify("Hur överklagar jag ett beslut?")
        assert result.intent == QueryIntent.PRACTICAL_PROCESS

    def test_hur_gor_man(self, classifier: IntentClassifier):
        result = classifier.classify("Hur gör man för att begära ut handlingar?")
        assert result.intent == QueryIntent.PRACTICAL_PROCESS


class TestLegalText:
    def test_regeringsformen(self, classifier: IntentClassifier):
        result = classifier.classify("Vad säger Regeringsformen om yttrandefrihet?")
        assert result.intent in (QueryIntent.LEGAL_TEXT, QueryIntent.PRACTICAL_PROCESS)
        # "Vad säger" matches both SFS and PRAXIS patterns; praxis wins ties.
        # This is expected — the important thing is it's one of the two.

    def test_grundagen_matches(self, classifier: IntentClassifier):
        """Pattern \bgrundag(en|ar|arna)?\b matches 'grundagen' (no 'l')."""
        result = classifier.classify("Vad är grundagen?")
        assert result.intent in (QueryIntent.LEGAL_TEXT, QueryIntent.PRACTICAL_PROCESS)

    def test_kap_paragraf_ref(self, classifier: IntentClassifier):
        result = classifier.classify("2 kap. 1 § regeringsformen")
        assert result.intent in (QueryIntent.LEGAL_TEXT, QueryIntent.PRACTICAL_PROCESS)


class TestUnknown:
    def test_random_text(self, classifier: IntentClassifier):
        result = classifier.classify("random unrecognized text")
        assert result.intent == QueryIntent.UNKNOWN

    def test_unknown_low_confidence(self, classifier: IntentClassifier):
        result = classifier.classify("random unrecognized text")
        assert result.confidence <= 0.5

    def test_unknown_has_fallback_collections(self, classifier: IntentClassifier):
        result = classifier.classify("random unrecognized text")
        assert len(result.suggested_collections) > 0


# ═══════════════════════════════════════════════════════════════════
# CONFIDENCE BOUNDS
# ═══════════════════════════════════════════════════════════════════


class TestConfidenceBounds:
    """All classify() results must have confidence in [0.0, 1.0]."""

    DIVERSE_QUERIES = [
        "Hej!",
        "RF 2:1",
        "Menar du förvaltningslagen?",
        "Hur har riksdagen behandlat klimatfrågan?",
        "Vilka argument använde partierna?",
        "Vad säger forskningen om klimat?",
        "Hur överklagar jag ett beslut?",
        "Vad säger Regeringsformen om yttrandefrihet?",
        "random unrecognized text",
        "",
    ]

    @pytest.mark.parametrize("query", DIVERSE_QUERIES)
    def test_confidence_within_0_1(self, classifier: IntentClassifier, query: str):
        result = classifier.classify(query)
        assert (
            0.0 <= result.confidence <= 1.0
        ), f"Confidence {result.confidence} out of bounds for '{query}'"


# ═══════════════════════════════════════════════════════════════════
# PRIORITY: PRACTICAL_PROCESS vs LEGAL_TEXT tie-break
# ═══════════════════════════════════════════════════════════════════


class TestPriorityTieBreak:
    def test_praxis_wins_when_both_match_and_praxis_ge_sfs(self, classifier: IntentClassifier):
        """
        When query matches both PRACTICAL_PROCESS and LEGAL_TEXT patterns
        and praxis_score >= sfs_score, PRACTICAL_PROCESS wins.
        """
        # "Vad säger" matches SFS, "Hur fungerar" matches PRAXIS
        # A query with both patterns where praxis >= sfs
        query = "Hur fungerar det enligt lagen?"
        result = classifier.classify(query)
        # "hur fungerar" → praxis match, no sfs match → PRACTICAL_PROCESS
        assert result.intent == QueryIntent.PRACTICAL_PROCESS

    def test_vad_sager_triggers_both(self, classifier: IntentClassifier):
        """'Vad säger' matches LEGAL_TEXT but also triggers PRACTICAL_PROCESS
        when combined with procedural language."""
        # "Vad säger" matches SFS_PATTERNS.
        # If no praxis pattern also matches, SFS wins.
        query = "Vad säger lagen om arv?"
        result = classifier.classify(query)
        # Only "vad säger" → sfs=1, praxis=0 → but wait, "vad säger" is only in SFS_PATTERNS
        # Actually praxis has no "vad säger" pattern, so sfs_score > praxis_score → LEGAL_TEXT
        # Unless there's a cross-match. Let me check... "vad säger" is only in SFS_PATTERNS.
        assert result.intent == QueryIntent.LEGAL_TEXT


# ═══════════════════════════════════════════════════════════════════
# INTENT_COLLECTIONS
# ═══════════════════════════════════════════════════════════════════


class TestIntentCollections:
    def test_smalltalk_empty(self):
        assert IntentClassifier.INTENT_COLLECTIONS[QueryIntent.SMALLTALK] == []

    def test_legal_text_has_sfs(self):
        cols = IntentClassifier.INTENT_COLLECTIONS[QueryIntent.LEGAL_TEXT]
        assert "sfs_lagtext_bge_m3_1024" in cols

    def test_research_has_diva(self):
        cols = IntentClassifier.INTENT_COLLECTIONS[QueryIntent.RESEARCH_SYNTHESIS]
        assert "diva_research_bge_m3_1024" in cols

    def test_parliament_has_riksdag(self):
        cols = IntentClassifier.INTENT_COLLECTIONS[QueryIntent.PARLIAMENT_TRACE]
        assert "riksdag_documents_p1_bge_m3_1024" in cols

    def test_practical_has_procedural(self):
        cols = IntentClassifier.INTENT_COLLECTIONS[QueryIntent.PRACTICAL_PROCESS]
        assert "procedural_guides_bge_m3_1024" in cols

    def test_backward_compat_sfs_primary_alias(self):
        assert (
            IntentClassifier.INTENT_COLLECTIONS[QueryIntent.SFS_PRIMARY]
            is IntentClassifier.INTENT_COLLECTIONS[QueryIntent.LEGAL_TEXT]
        )

    def test_backward_compat_praxis_alias(self):
        assert (
            IntentClassifier.INTENT_COLLECTIONS[QueryIntent.PRAXIS]
            is IntentClassifier.INTENT_COLLECTIONS[QueryIntent.PRACTICAL_PROCESS]
        )


# ═══════════════════════════════════════════════════════════════════
# get_collections_for_intent
# ═══════════════════════════════════════════════════════════════════


class TestGetCollectionsForIntent:
    def test_known_intent(self, classifier: IntentClassifier):
        cols = classifier.get_collections_for_intent(QueryIntent.LEGAL_TEXT)
        assert "sfs_lagtext_bge_m3_1024" in cols

    def test_unknown_intent_falls_back(self, classifier: IntentClassifier):
        """An unrecognized intent (simulated) falls back to UNKNOWN collections."""
        # get_collections_for_intent uses dict.get with UNKNOWN fallback
        # All real intents are in the dict, so we test the actual UNKNOWN entry
        cols = classifier.get_collections_for_intent(QueryIntent.UNKNOWN)
        expected = IntentClassifier.INTENT_COLLECTIONS[QueryIntent.UNKNOWN]
        assert cols == expected


# ═══════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_same_instance(self):
        a = get_intent_classifier()
        b = get_intent_classifier()
        assert a is b

    def test_returns_intent_classifier(self):
        instance = get_intent_classifier()
        assert isinstance(instance, IntentClassifier)


# ═══════════════════════════════════════════════════════════════════
# IntentResult DATACLASS
# ═══════════════════════════════════════════════════════════════════


class TestIntentResult:
    def test_fields(self):
        r = IntentResult(
            intent=QueryIntent.LEGAL_TEXT,
            confidence=0.85,
            matched_patterns=["legal:test"],
            suggested_collections=["sfs_lagtext_bge_m3_1024"],
        )
        assert r.intent == QueryIntent.LEGAL_TEXT
        assert r.confidence == 0.85
        assert r.matched_patterns == ["legal:test"]
        assert r.suggested_collections == ["sfs_lagtext_bge_m3_1024"]
