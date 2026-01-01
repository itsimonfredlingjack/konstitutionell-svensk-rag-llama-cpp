"""
Query Rewriter - Phase 2: Conversational Query Reformulation
=============================================================

Converts ambiguous conversational queries into standalone, search-optimized queries.

Key features:
- Decontextualization: "Vad säger den?" → "Vad säger GDPR?" (using history)
- Entity extraction: SFS numbers, myndigheter, lagar
- Guardrails: Prevent hallucination and drift

Research background:
- Conversational Query Reformulation (CQR) is well-established
- Key insight: Pronouns reference earlier context, embeddings can't resolve them
"""

import re
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set, Any

logger = logging.getLogger("constitutional.rewriter")


# ═══════════════════════════════════════════════════════════════════════════
# REWRITE RESULT
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RewriteResult:
    """Result of query rewriting."""
    original_query: str
    standalone_query: str       # Decontextualized, self-contained
    lexical_query: str          # For BM25/keyword boost
    must_include: List[str]     # Terms that MUST appear in results
    detected_entities: List[Dict[str, Any]] = field(default_factory=list)

    # Metrics for Phase 4
    rewrite_used: bool = True
    rewrite_latency_ms: float = 0.0
    needs_rewrite: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
# ENTITY PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

# Swedish legal entity patterns
ENTITY_PATTERNS = {
    "sfs": re.compile(r"(\d{4}:\d+)"),                    # 1998:204, 2018:218
    "kapitel": re.compile(r"(\d+)\s*kap\.?", re.IGNORECASE),  # 21 kap, 7 kap.
    "paragraf": re.compile(r"(\d+)\s*§"),                 # 14 §, 6 §
}

# Known Swedish legal abbreviations
LEGAL_ABBREVIATIONS = {
    "GDPR", "OSL", "RF", "TF", "YGL", "PuL", "BrB", "ÄB", "FB",
    "SekrL", "FörvL", "KL", "SoL", "LVU", "LVM", "HSL", "PSL",
    "MBL", "LAS", "AML", "SFB", "PBL", "MB",
}

# Known Swedish authorities (myndigheter)
AUTHORITIES = {
    "IMY", "Datainspektionen", "Riksdagen", "Regeringen", "Regeringskansliet",
    "Justitiedepartementet", "Socialdepartementet", "Finansdepartementet",
    "Skatteverket", "Försäkringskassan", "Arbetsförmedlingen", "Migrationsverket",
    "Polismyndigheten", "Åklagarmyndigheten", "Domstolsverket",
    "Socialstyrelsen", "Folkhälsomyndigheten", "IVO",
    "Konsumentverket", "Konkurrensverket", "Naturvårdsverket",
}

# Swedish pronouns that indicate reference to previous context
SWEDISH_PRONOUNS = {
    "den", "det", "dessa", "denna", "dette", "de", "dem",
    "hans", "hennes", "dess", "deras",
    "här", "där", "detta",
}


# ═══════════════════════════════════════════════════════════════════════════
# QUERY REWRITER
# ═══════════════════════════════════════════════════════════════════════════

class QueryRewriter:
    """
    Rewrites conversational queries into standalone search queries.

    Usage:
        rewriter = QueryRewriter()
        result = rewriter.rewrite(
            "Vad säger den om samtycke?",
            history=["Berätta om GDPR"]
        )
        # result.standalone_query = "Vad säger GDPR om samtycke?"
    """

    def __init__(self, llm_client=None):
        """
        Initialize QueryRewriter.

        Args:
            llm_client: Optional LLM client for complex rewrites (Phase 2+).
                       For now, we use regex-based rewriting only.
        """
        self.llm_client = llm_client
        self._pronoun_pattern = re.compile(
            r"\b(" + "|".join(SWEDISH_PRONOUNS) + r")\b",
            re.IGNORECASE
        )

    def needs_rewrite(self, query: str) -> bool:
        """
        Detect if query needs decontextualization.

        Returns True if query contains Swedish pronouns that likely
        reference previous context.
        """
        # Check for pronouns
        if self._pronoun_pattern.search(query):
            return True

        # Very short queries often need context
        if len(query.split()) <= 3:
            # But not if they contain explicit entities
            if not self._has_explicit_entities(query):
                return True

        return False

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract legal entities from text.

        Returns list of dicts with {type, value, confidence}.
        """
        entities = []

        # Extract SFS numbers
        for match in ENTITY_PATTERNS["sfs"].finditer(text):
            entities.append({
                "type": "sfs",
                "value": match.group(1),
                "confidence": 1.0,
            })

        # Extract chapter references
        for match in ENTITY_PATTERNS["kapitel"].finditer(text):
            entities.append({
                "type": "kapitel",
                "value": match.group(1),
                "confidence": 0.95,
            })

        # Extract paragraph references
        for match in ENTITY_PATTERNS["paragraf"].finditer(text):
            entities.append({
                "type": "paragraf",
                "value": match.group(1),
                "confidence": 0.95,
            })

        # Extract legal abbreviations
        for abbr in LEGAL_ABBREVIATIONS:
            # Match as whole word
            pattern = re.compile(r"\b" + re.escape(abbr) + r"\b", re.IGNORECASE)
            if pattern.search(text):
                entities.append({
                    "type": "lag",
                    "value": abbr.upper(),
                    "confidence": 0.9,
                })

        # Extract authorities
        for auth in AUTHORITIES:
            if auth.lower() in text.lower():
                entities.append({
                    "type": "myndighet",
                    "value": auth,
                    "confidence": 0.85,
                })

        return entities

    def decontextualize(
        self,
        query: str,
        history: Optional[List[str]] = None
    ) -> str:
        """
        Replace pronouns with referenced entities from history.

        Args:
            query: Current query with potential pronouns
            history: List of previous queries/messages in conversation

        Returns:
            Decontextualized query with pronouns replaced
        """
        if not history:
            return query

        # Extract entities from history (most recent first)
        history_entities = []
        for msg in reversed(history):
            entities = self.extract_entities(msg)
            history_entities.extend(entities)

        if not history_entities:
            return query

        # Find the most relevant entity to substitute
        # Priority: lag > myndighet > sfs > kapitel
        priority_order = ["lag", "myndighet", "sfs", "kapitel", "paragraf"]
        history_entities.sort(
            key=lambda e: (
                priority_order.index(e["type"]) if e["type"] in priority_order else 99,
                -e["confidence"]
            )
        )

        best_entity = history_entities[0] if history_entities else None

        if not best_entity:
            return query

        # Replace pronouns with the entity
        # Simple pattern: replace first pronoun with entity value
        result = self._pronoun_pattern.sub(
            best_entity["value"],
            query,
            count=1  # Only replace first pronoun
        )

        return result

    def rewrite(
        self,
        query: str,
        history: Optional[List[str]] = None
    ) -> RewriteResult:
        """
        Main rewriting method.

        Args:
            query: User's query
            history: Conversation history for decontextualization

        Returns:
            RewriteResult with standalone_query, lexical_query, etc.
        """
        start = time.perf_counter()

        # Check if rewrite is needed
        query_needs_rewrite = self.needs_rewrite(query)

        # Decontextualize if needed
        if query_needs_rewrite and history:
            standalone_query = self.decontextualize(query, history)
        else:
            standalone_query = query

        # Extract entities from final query
        detected_entities = self.extract_entities(standalone_query)

        # Build must_include list (entities that MUST appear in results)
        must_include = [
            e["value"] for e in detected_entities
            if e["type"] in ("lag", "sfs") and e["confidence"] >= 0.9
        ]

        # Build lexical query (for BM25 boost)
        lexical_query = self._build_lexical_query(standalone_query, detected_entities)

        latency_ms = (time.perf_counter() - start) * 1000

        result = RewriteResult(
            original_query=query,
            standalone_query=standalone_query,
            lexical_query=lexical_query,
            must_include=must_include,
            detected_entities=detected_entities,
            rewrite_used=query_needs_rewrite,
            rewrite_latency_ms=latency_ms,
            needs_rewrite=query_needs_rewrite,
        )

        logger.info(
            f"Query rewrite: '{query}' → '{standalone_query}' "
            f"(entities: {len(detected_entities)}, latency: {latency_ms:.2f}ms)"
        )

        return result

    def _has_explicit_entities(self, text: str) -> bool:
        """Check if text contains explicit legal entities."""
        entities = self.extract_entities(text)
        return len(entities) > 0

    def _build_lexical_query(
        self,
        query: str,
        entities: List[Dict[str, Any]]
    ) -> str:
        """
        Build a lexical query for BM25/keyword search.

        Extracts key terms and entities for exact matching.
        """
        terms = []

        # Add entity values
        for entity in entities:
            terms.append(entity["value"])

        # Add significant words from query (excluding stopwords)
        swedish_stopwords = {
            "och", "i", "att", "det", "som", "en", "på", "är", "av", "för",
            "med", "till", "den", "har", "de", "inte", "om", "ett", "kan",
            "ska", "jag", "vi", "du", "vad", "hur", "när", "var", "vilka",
            "finns", "eller", "men", "så", "nu", "bara", "alla", "också",
            "efter", "vid", "från", "ut", "upp", "in", "över", "sin",
            "säger", "enligt", "gäller", "berätta",
        }

        words = re.findall(r"\b\w+\b", query.lower())
        for word in words:
            if word not in swedish_stopwords and len(word) > 2:
                if word not in [t.lower() for t in terms]:
                    terms.append(word)

        return " ".join(terms)


# ═══════════════════════════════════════════════════════════════════════════
# GUARDRAILS
# ═══════════════════════════════════════════════════════════════════════════

def validate_must_include(
    result: RewriteResult,
    search_results: List[Dict[str, Any]]
) -> bool:
    """
    Guardrail 1: Every must_include term must appear in at least 1 top-k result.

    Args:
        result: RewriteResult with must_include terms
        search_results: List of search result dicts with 'snippet' field

    Returns:
        True if all must_include terms are found, False otherwise
    """
    for term in result.must_include:
        found = any(
            term.lower() in doc.get("snippet", "").lower()
            for doc in search_results[:10]
        )
        if not found:
            logger.warning(f"Guardrail 1 failed: must_include term '{term}' not in results")
            return False
    return True


def validate_no_hallucination(
    original: str,
    standalone: str,
    history: Optional[List[str]] = None
) -> bool:
    """
    Guardrail 2: Standalone query should not introduce entities not in original + history.

    Returns:
        True if no hallucinated entities, False otherwise
    """
    rewriter = QueryRewriter()

    # Get entities from original + history
    allowed_entities = set()
    for entity in rewriter.extract_entities(original):
        allowed_entities.add(entity["value"].lower())

    if history:
        for msg in history:
            for entity in rewriter.extract_entities(msg):
                allowed_entities.add(entity["value"].lower())

    # Get entities from standalone
    standalone_entities = set()
    for entity in rewriter.extract_entities(standalone):
        standalone_entities.add(entity["value"].lower())

    # Check for new entities
    new_entities = standalone_entities - allowed_entities
    if new_entities:
        logger.warning(f"Guardrail 2 failed: hallucinated entities {new_entities}")
        return False

    return True


def validate_sanity(original: str, standalone: str) -> bool:
    """
    Guardrail 3: Standalone should be similar length and topic.

    Returns:
        True if sanity check passes, False otherwise
    """
    if len(original) == 0:
        return True

    length_ratio = len(standalone) / len(original)

    if not (0.5 <= length_ratio <= 3.0):
        logger.warning(
            f"Guardrail 3 failed: length ratio {length_ratio:.2f} "
            f"(original: {len(original)}, standalone: {len(standalone)})"
        )
        return False

    return True
