"""
Intent Classifier for Constitutional-AI RAG
Detects query intent to route to appropriate collections.

Intent Types:
- LEGAL_TEXT: Legal/factual questions about specific laws (was SFS_PRIMARY)
- PRACTICAL_PROCESS: Procedural "how to" questions (was PRAXIS)
- PARLIAMENT_TRACE: Questions about riksdag/parliament process
- POLICY_ARGUMENTS: Questions about political arguments and positions
- RESEARCH_SYNTHESIS: Questions about research/evidence
- EDGE: Edge cases (abbreviations, clarifications)
- SMALLTALK: Greetings and off-topic
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List

logger = logging.getLogger("constitutional.intent")


class QueryIntent(str, Enum):
    """Query intent categories for collection routing."""

    # Primary intents (new naming)
    LEGAL_TEXT = "legal_text"  # "Vad säger lagen?"
    PARLIAMENT_TRACE = "parliament_trace"  # "Hur har riksdagen behandlat X?"
    POLICY_ARGUMENTS = "policy_arguments"  # "Vilka argument använde partierna?"
    RESEARCH_SYNTHESIS = "research"  # "Vad säger forskningen?"
    PRACTICAL_PROCESS = "practical"  # "Hur överklagar jag?"

    # Edge cases
    EDGE_ABBREVIATION = "edge_abbr"  # Law abbreviations (RF, TF, OSL)
    EDGE_CLARIFICATION = "edge_clar"  # Disambiguation queries

    # Meta intents
    SMALLTALK = "smalltalk"  # Greetings, off-topic
    UNKNOWN = "unknown"  # Default

    # Backward compatibility aliases - these resolve to the same values
    SFS_PRIMARY = "legal_text"  # Alias for LEGAL_TEXT
    PRAXIS = "practical"  # Alias for PRACTICAL_PROCESS


@dataclass
class IntentResult:
    """Result of intent classification."""

    intent: QueryIntent
    confidence: float  # 0.0-1.0
    matched_patterns: List[str]
    suggested_collections: List[str]


class IntentClassifier:
    """
    Rule-based intent classifier for Swedish constitutional queries.

    Uses keyword patterns to detect various query intents for routing
    to appropriate document collections.
    """

    # ==================== Pattern Definitions ====================

    # Parliament process patterns (PARLIAMENT_TRACE)
    PARLIAMENT_PATTERNS = [
        r"\bhur\s+har\s+riksdagen\s+behandlat\b",
        r"\bhur\s+behandlades\b",
        r"\bvilket\s+utskott\b",
        r"\bbetänkande(t|n)?\b",
        r"\bvotering(en)?\b",
        r"\bhur\s+röstade\b",
        r"\bproposition(en)?\s+(om|gällande)\b",
        r"\briksdagsbeslut\b",
        r"\butskottsbehandling\b",
    ]

    # Policy argument patterns (POLICY_ARGUMENTS)
    POLICY_ARG_PATTERNS = [
        r"\bvilka\s+argument\b",
        r"\bvad\s+(sa|sade|menade)\s+(partierna|oppositionen|regeringen)\b",
        r"\bvilka\s+partier\s+(var\s+för|stödde|motsatte)\b",
        r"\bpolitisk(a)?\s+(argument|position|ståndpunkt)\b",
        r"\bkritik(en)?\s+mot\b",
    ]

    # Research synthesis patterns (RESEARCH_SYNTHESIS)
    RESEARCH_PATTERNS = [
        r"\bvad\s+säger\s+forskningen\b",
        r"\bevidens\s+(för|om|visar|finns)\b",
        r"\bstudier\s+(visar|om)\b",
        r"\bforskningsläge(t)?\b",
        r"\bmeta-?analys\b",
        r"\bvetenskaplig(a|t)?\s+(stöd|belägg)\b",
        r"\bakademisk(a)?\s+(forskning|studie|rapport)\b",
        r"\bavhandling(ar|en)?\b",
        r"\buppsats(er|en)?\b",
        r"\bdoktorsavhandling(ar)?\b",
        r"\bempirisk(a)?\s+(studie|undersökning|data)\b",
        r"\bundersökning(ar|en)?\s+(visar|om)\b",
        r"\blitteraturöversikt(en)?\b",
        r"\bsystematisk\s+översikt\b",
        r"\bforskningsresultat(en|et)?\b",
        r"\bvad\s+visar\s+forskning(en)?\b",
    ]

    # Procedural patterns (PRACTICAL_PROCESS, was PRAXIS)
    PRAXIS_PATTERNS = [
        r"\bhur\s+fungerar\b",
        r"\bhur\s+gör\s+(man|jag)\b",
        r"\bhur\s+begär\b",
        r"\bhur\s+överklagar\b",
        r"\bhur\s+ansöker\b",
        r"\bhur\s+får\s+(man|jag)\b",
        r"\bhur\s+kan\s+(man|jag)\b",
        r"\bvilka\s+steg\b",
        r"\bvad\s+är\s+processen\b",
        r"\bvad\s+innebär\s+\w*skyldighet",
        r"\bvad\s+innebär\s+\w*princip",
        r"\bskillnaden\s+mellan\b",  # "Vad är skillnaden mellan X och Y?"
        r"\bsteg\s+för\s+steg\b",
        r"\bpraktiskt\b",
        r"\bi\s+praktiken\b",
    ]

    # Legal reference patterns (LEGAL_TEXT, was SFS_PRIMARY)
    SFS_PATTERNS = [
        r"\bvad\s+säger\b",
        r"\benligt\s+(RF|TF|YGL|OSL|FL|BrB|RB)",
        r"\bvad\s+står\s+i\b",
        r"\b(regeringsformen|tryckfrihetsförordningen|yttrandefrihetsgrundlagen)\b",
        r"\b(offentlighets-?\s*och\s*sekretesslagen|förvaltningslagen|brottsbalken)\b",
        r"\bvilka\s+(grundläggande\s+)?rättigheter\b",
        r"\bvilka\s+fri-?\s*och\s*rättigheter\b",
        r"\bgrundag(en|ar|arna)?\b",
        r"\b\d+\s*kap\.?\s*\d*\s*§\b",  # "2 kap. 1 §"
    ]

    # Abbreviation patterns (EDGE)
    ABBREV_PATTERNS = [
        r"\b(RF|TF|YGL|OSL|FL|BrB|RB)\s+\d+[:\s]*\d*\b",  # "RF 2:1"
        r"\bvad\s+står\s+i\s+(RF|TF|YGL|OSL)\s+\d+",  # "vad står i OSL 21:7"
    ]

    # Clarification patterns (EDGE)
    CLARIFICATION_PATTERNS = [
        r"\bmenar\s+du\b",
        r"\bvilken\s+(av|mellan)\b",
    ]

    # Smalltalk patterns
    SMALLTALK_PATTERNS = [
        r"^hej\b",
        r"^hallå\b",
        r"^god\s+(morgon|dag|kväll)\b",
        r"\bhur\s+mår\s+(du|ni)\b",
        r"\bvad\s+är\s+klockan\b",
        r"^tack\b",
    ]

    # ==================== Collection Routing ====================

    INTENT_COLLECTIONS = {
        QueryIntent.PARLIAMENT_TRACE: [
            "riksdag_documents_p1_bge_m3_1024",  # Primary: riksdag docs
            "swedish_gov_docs_bge_m3_1024",
            "sfs_lagtext_bge_m3_1024",
        ],
        QueryIntent.POLICY_ARGUMENTS: [
            "riksdag_documents_p1_bge_m3_1024",  # Primary: party debates/motions
            "swedish_gov_docs_bge_m3_1024",
        ],
        QueryIntent.RESEARCH_SYNTHESIS: [
            "diva_research_bge_m3_1024",  # Primary: akademisk forskning
            "swedish_gov_docs_bge_m3_1024",
            "riksdag_documents_p1_bge_m3_1024",
        ],
        QueryIntent.PRACTICAL_PROCESS: [
            "procedural_guides_bge_m3_1024",  # Primary: procedural guides
            "sfs_lagtext_bge_m3_1024",
            "swedish_gov_docs_bge_m3_1024",
            "riksdag_documents_p1_bge_m3_1024",
        ],
        QueryIntent.LEGAL_TEXT: [
            "sfs_lagtext_bge_m3_1024",  # Primary: law text
            "riksdag_documents_p1_bge_m3_1024",
            "swedish_gov_docs_bge_m3_1024",
        ],
        QueryIntent.EDGE_ABBREVIATION: [
            "sfs_lagtext_bge_m3_1024",
            "riksdag_documents_p1_bge_m3_1024",
        ],
        QueryIntent.EDGE_CLARIFICATION: [
            "sfs_lagtext_bge_m3_1024",
            "swedish_gov_docs_bge_m3_1024",
        ],
        QueryIntent.SMALLTALK: [],  # No retrieval needed
        QueryIntent.UNKNOWN: [
            "sfs_lagtext_bge_m3_1024",
            "riksdag_documents_p1_bge_m3_1024",
            "swedish_gov_docs_bge_m3_1024",
        ],
    }

    # Add aliases for backward compatibility
    INTENT_COLLECTIONS[QueryIntent.SFS_PRIMARY] = INTENT_COLLECTIONS[QueryIntent.LEGAL_TEXT]
    INTENT_COLLECTIONS[QueryIntent.PRAXIS] = INTENT_COLLECTIONS[QueryIntent.PRACTICAL_PROCESS]

    def __init__(self):
        """Compile regex patterns for efficiency."""
        self._parliament_re = [re.compile(p, re.IGNORECASE) for p in self.PARLIAMENT_PATTERNS]
        self._policy_arg_re = [re.compile(p, re.IGNORECASE) for p in self.POLICY_ARG_PATTERNS]
        self._research_re = [re.compile(p, re.IGNORECASE) for p in self.RESEARCH_PATTERNS]
        self._praxis_re = [re.compile(p, re.IGNORECASE) for p in self.PRAXIS_PATTERNS]
        self._sfs_re = [re.compile(p, re.IGNORECASE) for p in self.SFS_PATTERNS]
        self._abbrev_re = [re.compile(p, re.IGNORECASE) for p in self.ABBREV_PATTERNS]
        self._clar_re = [re.compile(p, re.IGNORECASE) for p in self.CLARIFICATION_PATTERNS]
        self._small_re = [re.compile(p, re.IGNORECASE) for p in self.SMALLTALK_PATTERNS]

    def classify(self, query: str) -> IntentResult:
        """
        Classify query intent and return suggested collections.

        Priority order:
        1. SMALLTALK (short-circuit)
        2. EDGE_ABBREVIATION
        3. EDGE_CLARIFICATION
        4. PARLIAMENT_TRACE (new)
        5. POLICY_ARGUMENTS (new)
        6. RESEARCH_SYNTHESIS (new)
        7. PRACTICAL_PROCESS (was PRAXIS)
        8. LEGAL_TEXT (was SFS_PRIMARY)
        9. UNKNOWN (default)

        Args:
            query: User query string

        Returns:
            IntentResult with intent, confidence, and suggested collections
        """
        query_lower = query.lower().strip()
        matched = []

        # 1. Smalltalk (highest priority - short circuit)
        for pattern in self._small_re:
            if pattern.search(query_lower):
                matched.append(f"smalltalk:{pattern.pattern}")
        if matched:
            return IntentResult(
                intent=QueryIntent.SMALLTALK,
                confidence=0.95,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.SMALLTALK],
            )

        # 2. Edge: Abbreviations (e.g., "RF 2:1")
        matched = []
        for pattern in self._abbrev_re:
            if pattern.search(query_lower):
                matched.append(f"abbrev:{pattern.pattern}")
        if matched:
            return IntentResult(
                intent=QueryIntent.EDGE_ABBREVIATION,
                confidence=0.90,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.EDGE_ABBREVIATION],
            )

        # 3. Edge: Clarification
        matched = []
        for pattern in self._clar_re:
            if pattern.search(query_lower):
                matched.append(f"clar:{pattern.pattern}")
        if matched:
            return IntentResult(
                intent=QueryIntent.EDGE_CLARIFICATION,
                confidence=0.85,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.EDGE_CLARIFICATION],
            )

        # 4. PARLIAMENT_TRACE (new - check early for riksdag-specific queries)
        matched = []
        for pattern in self._parliament_re:
            if pattern.search(query_lower):
                matched.append(f"parliament:{pattern.pattern}")
        if matched:
            confidence = min(0.70 + len(matched) * 0.10, 0.95)
            return IntentResult(
                intent=QueryIntent.PARLIAMENT_TRACE,
                confidence=confidence,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.PARLIAMENT_TRACE],
            )

        # 5. POLICY_ARGUMENTS (new - political argument queries)
        matched = []
        for pattern in self._policy_arg_re:
            if pattern.search(query_lower):
                matched.append(f"policy_arg:{pattern.pattern}")
        if matched:
            confidence = min(0.70 + len(matched) * 0.10, 0.95)
            return IntentResult(
                intent=QueryIntent.POLICY_ARGUMENTS,
                confidence=confidence,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.POLICY_ARGUMENTS],
            )

        # 6. RESEARCH_SYNTHESIS (new - research/evidence queries)
        matched = []
        for pattern in self._research_re:
            if pattern.search(query_lower):
                matched.append(f"research:{pattern.pattern}")
        if matched:
            confidence = min(0.70 + len(matched) * 0.10, 0.95)
            return IntentResult(
                intent=QueryIntent.RESEARCH_SYNTHESIS,
                confidence=confidence,
                matched_patterns=matched,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.RESEARCH_SYNTHESIS],
            )

        # 7. PRACTICAL_PROCESS (was PRAXIS - procedural)
        praxis_matches = []
        for pattern in self._praxis_re:
            if pattern.search(query_lower):
                praxis_matches.append(f"practical:{pattern.pattern}")

        # 8. LEGAL_TEXT (was SFS_PRIMARY - legal references)
        sfs_matches = []
        for pattern in self._sfs_re:
            if pattern.search(query_lower):
                sfs_matches.append(f"legal:{pattern.pattern}")

        # Determine winner based on match count and strength
        praxis_score = len(praxis_matches)
        sfs_score = len(sfs_matches)

        if praxis_score > 0 and praxis_score >= sfs_score:
            # PRACTICAL_PROCESS wins or ties (prefer procedural for how-to questions)
            confidence = min(0.60 + praxis_score * 0.15, 0.95)
            return IntentResult(
                intent=QueryIntent.PRACTICAL_PROCESS,
                confidence=confidence,
                matched_patterns=praxis_matches,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.PRACTICAL_PROCESS],
            )
        elif sfs_score > 0:
            # LEGAL_TEXT wins
            confidence = min(0.60 + sfs_score * 0.15, 0.95)
            return IntentResult(
                intent=QueryIntent.LEGAL_TEXT,
                confidence=confidence,
                matched_patterns=sfs_matches,
                suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.LEGAL_TEXT],
            )

        # 9. Default: Unknown intent, use all collections
        return IntentResult(
            intent=QueryIntent.UNKNOWN,
            confidence=0.30,
            matched_patterns=[],
            suggested_collections=self.INTENT_COLLECTIONS[QueryIntent.UNKNOWN],
        )

    def get_collections_for_intent(self, intent: QueryIntent) -> List[str]:
        """Get collection list for a given intent."""
        return self.INTENT_COLLECTIONS.get(intent, self.INTENT_COLLECTIONS[QueryIntent.UNKNOWN])


# Singleton instance
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Get singleton IntentClassifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance


# Quick test
if __name__ == "__main__":
    classifier = IntentClassifier()

    test_queries = [
        # New intents
        "Hur har riksdagen behandlat klimatfrågan?",
        "Vilket utskott hanterade propositionen?",
        "Vilka argument använde Socialdemokraterna?",
        "Vad var oppositionens kritik mot förslaget?",
        "Vad säger forskningen om klimatförändringar?",
        "Vilken evidens finns för detta?",
        # Existing intents
        "Hur överklagar jag ett myndighetsbeslut?",
        "Vad säger Regeringsformen om yttrandefrihet?",
        "Vad säger RF 2:1?",
        "Menar du förvaltningslagen eller förvaltningsprocesslagen?",
        "Hej, hur mår du?",
        "Vilka grundläggande rättigheter skyddas i RF 2 kap?",
    ]

    print("Intent Classification Test (EPR Extended):")
    print("-" * 80)
    for q in test_queries:
        result = classifier.classify(q)
        print(f"Q: {q[:60]}...")
        print(f"   Intent: {result.intent.value} (conf: {result.confidence:.2f})")
        print(f"   Collections: {', '.join(result.suggested_collections[:2])}...")
        print()
