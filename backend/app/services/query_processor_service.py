"""
Query Processor Service - Classification and Decontextualization
Handles query classification (CHAT/ASSIST/EVIDENCE) and conversation history
"""

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService

logger = get_logger(__name__)


class ResponseMode(str, Enum):
    """
    Response modes for Constitutional AI.

    Each mode has different system prompts and model configurations.
    """

    CHAT = "chat"  # Smalltalk, greetings, meta-questions
    ASSIST = "assist"  # Default - dual-pass with fact+style
    EVIDENCE = "evidence"  # Formal legal queries with citations


class EvidenceLevel(str, Enum):
    """
    Evidence confidence levels based on source quality.

    Used to determine answer style and strictness.
    """

    HIGH = "high"  # Multiple high-scoring SFS/prop sources
    MEDIUM = "medium"  # Multiple sources with reasonable quality
    LOW = "low"  # Some relevant sources but lower scores
    NONE = "none"  # No relevant sources found


@dataclass
class QueryClassification:
    """
    Result of query classification.

    Attributes:
        mode: Response mode (chat/assist/evidence)
        reason: Human-readable reason for classification
    """

    mode: ResponseMode
    reason: str


@dataclass
class DecontextualizedQuery:
    """
    Result of query decontextualization.

    Attributes:
        original_query: The user's original query
        rewritten_query: Standalone version with context
        detected_entities: Legal entities detected (GDPR, OSL, etc.)
        confidence: Confidence score of the rewrite (0-1)
    """

    original_query: str
    rewritten_query: str
    detected_entities: List[str]
    confidence: float


class QueryProcessorService(BaseService):
    """
    Query Processor Service.

    Handles:
    - Query classification into CHAT/ASSIST/EVIDENCE modes
    - Query decontextualization from conversation history
    - Entity extraction for legal terms
    - Confidence scoring for rewrites
    """

    # CHAT mode patterns - smalltalk, greetings, meta-questions
    CHAT_PATTERNS = [
        r"^(hej|tjena|hallå|hejsan|god\s+(morgon|dag|kväll))[\s!?]*$",
        r"^(tack|tackar|bra jobbat|fint)[\s!?]*$",
        r"^(vem är du|vad kan du|hur funkar du)[\s!?]*",
        r"^(ja|nej|ok|okej|alright)[\s!?]*$",
    ]

    # EVIDENCE mode patterns - explicit legal references, citations requested
    EVIDENCE_PATTERNS = [
        r"vad säger (lagen|lagstiftningen|rf|gdpr|osl|tf)",
        r"enligt \d+\s*(kap|§|kapitel)",
        r"visa (paragrafen|lagtext|källa|citera)\s*",
        r"(sfs|prop|sou)\s*\d{4}:\d+",
    ]

    # Swedish stopwords to filter out
    SWEDISH_STOPWORDS = {
        "och",
        "i",
        "att",
        "en",
        "ett",
        "det",
        "som",
        "av",
        "för",
        "med",
        "till",
        "på",
        "är",
        "om",
        "har",
        "de",
        "den",
        "vara",
        "vad",
        "var",
        "hur",
        "när",
        "kan",
        "ska",
        "inte",
        "eller",
        "men",
        "så",
        "från",
        "vid",
        "ut",
        "upp",
        "få",
        "ta",
        "ge",
        "göra",
        "finns",
        "alla",
        "än",
        "dessa",
        "detta",
        "vilka",
        "vilket",
        "vilken",
        "sin",
        "sina",
        "sig",
        "oss",
        "vi",
        "ni",
        "dom",
        "dem",
        "deras",
        "vår",
        "vårt",
        "våra",
        "han",
        "hon",
        "hennes",
        "hans",
        "ja",
        "nej",
        "bara",
        "mycket",
        "mer",
        "mest",
        "enligt",
        "säger",
        "gäller",
        "berätta",
        "förklara",
        "beskriv",
    }

    # Legal entity detection patterns
    LEGAL_ENTITY_PATTERNS = [
        r"(GDPR|gdpr)",  # General Data Protection Regulation
        r"(OSL|osl|offentlighets.*lagen)",  # Public Access to Information and Secrecy Act
        r"(TF|tf|tryckfrihetsförordningen)",  # Fundamental Law on Freedom of Expression
        r"(RF|rf|regeringsformen)",  # Instrument of Government
        r"(SFS\s*\d{4}:\d+)",  # Swedish Code of Statutes
        r"(prop\.\s*\d{4}/\d{2,4}:\d+)",  # Government bills
        r"(SOU\s*\d{4}:\d+)",  # Official Government Reports
        r"(personuppgiftslagen|pul)",  # Personal Data Act (deprecated)
    ]

    def __init__(self, config: ConfigService):
        """
        Initialize Query Processor Service.

        Args:
            config: ConfigService for model configuration
        """
        super().__init__(config)
        self.logger.info("Query Processor Service initialized")

    async def initialize(self) -> None:
        """
        Initialize query processor (loads patterns, etc.).
        """
        self._mark_initialized()

    async def health_check(self) -> bool:
        """
        Check if service is healthy.
        """
        return True  # Always healthy (no external dependencies)

    async def close(self) -> None:
        """
        Cleanup resources.
        """
        self._mark_uninitialized()

    def classify_query(self, query: str) -> QueryClassification:
        """
        Classify a query into CHAT/ASSIST/EVIDENCE mode.

        Args:
            query: User's question

        Returns:
            QueryClassification with mode and reason

        Algorithm:
            1. Check CHAT patterns first (smalltalk)
            2. Check EVIDENCE patterns (legal citations)
            3. Default to ASSIST if neither match
        """
        query_lower = query.lower().strip()

        # Check CHAT patterns first
        for pattern in self.CHAT_PATTERNS:
            if re.match(pattern, query_lower, re.IGNORECASE):
                return QueryClassification(
                    mode=ResponseMode.CHAT, reason=f"Matched CHAT pattern: {pattern}"
                )

        # Check EVIDENCE patterns
        for pattern in self.EVIDENCE_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return QueryClassification(
                    mode=ResponseMode.EVIDENCE, reason=f"Matched EVIDENCE pattern: {pattern}"
                )

        # Default to ASSIST
        return QueryClassification(
            mode=ResponseMode.ASSIST,
            reason="Default classification (neither CHAT nor EVIDENCE patterns)",
        )

    def decontextualize_query(self, query: str, history: List[dict]) -> DecontextualizedQuery:
        """
        Rewrite a follow-up question to be standalone using conversation history.

        Examples:
        - "Vad sa den om straff?" + history about GDPR → "Vad säger GDPR om straff?"
        - "Och enligt OSL?" + history about sekretess → "Och enligt Offentlighets- och Sekretesslagen om sekretess?"

        Args:
            query: Follow-up question
            history: Conversation history (last 6 messages)

        Returns:
            DecontextualizedQuery with rewritten query and confidence
        """
        if not history or len(history) < 2:
            # No context available
            return DecontextualizedQuery(
                original_query=query,
                rewritten_query=query,
                detected_entities=[],
                confidence=0.0,
            )

        query_lower = query.lower().strip()

        # Patterns that indicate a follow-up question
        followup_patterns = [
            r"^och\s+",  # "Och vad gäller..."
            r"^men\s+",  # "Men om..."
            r"^vad\s+med\s+",  # "Vad med..."
            r"^hur\s+är\s+det\s+med",  # "Hur är det med..."
            r"^den\s+",  # "Den lagen..." (referring back)
            r"^det\s+",  # "Det kapitlet..." (referring back)
            r"^samma\s+",  # "Samma sak för..."
            r"^enligt\s+\w+\?$",  # Short "enligt X?" questions
        ]

        # Check if this looks like a follow-up
        is_followup = any(re.match(pattern, query_lower) for pattern in followup_patterns)

        if not is_followup and len(query) > 30:
            # Long questions are usually self-contained
            return DecontextualizedQuery(
                original_query=query,
                rewritten_query=query,
                detected_entities=[],
                confidence=0.5,
            )

        # Extract context from last user question and assistant response
        last_user_q = None
        last_assistant_response = None

        for msg in reversed(history[-6:]):
            if msg.get("role") == "user" and not last_user_q:
                last_user_q = msg.get("content", "")
            elif msg.get("role") == "assistant" and not last_assistant_response:
                last_assistant_response = msg.get("content", "")

            if last_user_q and last_assistant_response:
                break

        if not last_user_q:
            return DecontextualizedQuery(
                original_query=query,
                rewritten_query=query,
                detected_entities=[],
                confidence=0.3,
            )

        # Extract legal entities from previous context
        detected_entities = self._extract_legal_entities(f"{last_user_q} {last_assistant_response}")

        if not detected_entities:
            return DecontextualizedQuery(
                original_query=query,
                rewritten_query=query,
                detected_entities=[],
                confidence=0.4,
            )

        # Decontextualize: add context to question
        unique_entities = []
        seen = set()
        for entity in detected_entities:
            entity_lower = entity.lower() if isinstance(entity, str) else str(entity).lower()
            if entity_lower not in seen:
                unique_entities.append(entity)
                seen.add(entity_lower)

        context_str = ", ".join(unique_entities[:3])  # Max 3 entities
        confidence = min(0.9, 0.5 + len(unique_entities) * 0.1)  # More entities = higher confidence

        # Construct decontextualized query
        if is_followup:
            # For clear follow-ups, prepend context
            rewritten = f"Angående {context_str}: {query}"
        else:
            # For short questions, append context
            rewritten = f"{query} (kontext: {context_str})"

        self.logger.info(
            f"Decontextualized: '{query}' → '{rewritten}' "
            f"(confidence: {confidence:.2f}, entities: {detected_entities})"
        )

        return DecontextualizedQuery(
            original_query=query,
            rewritten_query=rewritten,
            detected_entities=detected_entities,
            confidence=confidence,
        )

    def _extract_legal_entities(self, text: str) -> List[str]:
        """
        Extract legal entities from text.

        Looks for Swedish legal abbreviations and references.

        Args:
            text: Text to analyze

        Returns:
            List of detected legal entities
        """
        entities = []
        text_lower = text.lower()

        for pattern in self.LEGAL_ENTITY_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                # Normalize to uppercase for consistency
                normalized = match.upper()
                if normalized not in entities:
                    entities.append(normalized)

        return entities

    def extract_search_keywords(self, query: str) -> List[str]:
        """
        Extract meaningful keywords from a question for text search.

        Removes stopwords and question phrases, returns terms sorted by length.
        Swedish compound words are typically longer and more informative.

        Args:
            query: User's question

        Returns:
            List of keywords sorted by length (longest first)
        """
        # Remove common question phrases first
        clean_query = query.lower()
        question_phrases = [
            r"^vad är\s+",
            r"^vad säger\s+",
            r"^vad innebär\s+",
            r"^hur fungerar\s+",
            r"^hur funkar\s+",
            r"^berätta om\s+",
            r"^förklara\s+",
            r"^beskriv\s+",
            r"^vilka\s+",
            r"^vilket\s+",
            r"^vilken\s+",
        ]
        for phrase in question_phrases:
            clean_query = re.sub(phrase, "", clean_query)

        # Remove punctuation
        clean_query = re.sub(r'[?!.,;:"\']', "", clean_query)

        # Split into words
        words = clean_query.split()

        # Filter out stopwords and short words
        keywords = [w for w in words if w not in self.SWEDISH_STOPWORDS and len(w) >= 3]

        # Remove duplicates while preserving first occurrence
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        # Sort by length (longest first) - Swedish compound words are most informative
        unique_keywords.sort(key=len, reverse=True)

        return unique_keywords

    def determine_evidence_level(self, sources: List[dict], answer: str) -> EvidenceLevel:
        """
        Determine evidence level based on source quality.

        HIGH: Multiple high-scoring SFS/prop sources
        MEDIUM: Multiple sources with reasonable quality
        LOW: Some relevant sources but lower scores
        NONE: No relevant sources found

        Args:
            sources: List of source dictionaries with 'score' and 'doc_type'
            answer: Generated answer (optional for future improvements)

        Returns:
            EvidenceLevel enum value
        """
        if not sources:
            return EvidenceLevel.NONE

        # Count high-quality sources (score > 0.55, SFS or prop type)
        high_quality = sum(
            1 for s in sources if s.get("score", 0) > 0.55 and s.get("doc_type") in ["sfs", "prop"]
        )

        # Average score
        avg_score = sum(s.get("score", 0) for s in sources) / len(sources)

        if high_quality >= 2 or avg_score > 0.60:
            return EvidenceLevel.HIGH
        elif len(sources) >= 3 or (len(sources) >= 2 and avg_score > 0.45):
            return EvidenceLevel.MEDIUM
        elif len(sources) > 0 and avg_score > 0.3:
            return EvidenceLevel.LOW
        else:
            return EvidenceLevel.NONE

    def get_mode_config(self, mode: str) -> dict:
        """
        Get model configuration for a specific response mode.

        Maps mode names to pre-configured model settings.

        Args:
            mode: Response mode (chat/assist/evidence)

        Returns:
            Dictionary with model configuration (temperature, top_p, etc.)
        """
        mode_map = {
            "chat": ResponseMode.CHAT,
            "assist": ResponseMode.ASSIST,
            "evidence": ResponseMode.EVIDENCE,
        }

        mode_enum = mode_map.get(mode.lower(), ResponseMode.ASSIST)
        return self.config.get_mode_config(mode_enum.value)


# Singleton instance cache
_query_processor_instance: Optional[QueryProcessorService] = None
_query_processor_lock = asyncio.Lock()


def get_query_processor_service(config: Optional[ConfigService] = None) -> QueryProcessorService:
    """
    Get singleton QueryProcessorService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Singleton QueryProcessorService instance
    """
    global _query_processor_instance, _query_processor_lock

    if _query_processor_instance is None:
        # Get config if not provided
        if config is None:
            from .config_service import get_config_service

            config = get_config_service()

        # Initialize service
        _query_processor_instance = QueryProcessorService(config=config)

    return _query_processor_instance
