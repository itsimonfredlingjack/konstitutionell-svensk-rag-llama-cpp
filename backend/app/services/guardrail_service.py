"""
Guardrail Service - Jail Warden v2
Post-processing service for legal term corrections and security validation
"""

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import List, Optional, Tuple

from ..core.exceptions import SecurityViolationError
from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service

logger = get_logger(__name__)


class WardenStatus(str, Enum):
    """
    Jail Warden status codes.

    Different types of corrections and violations detected.
    """

    UNCHANGED = "unchanged"  # No corrections needed
    TERM_CORRECTED = "term_corrected"  # Outdated terms corrected
    QUESTION_REWRITTEN = "question_rewritten"  # Query was rewritten for clarity
    FACT_VERIFIED = "fact_verified"  # Facts were verified against corpus
    FACT_UNVERIFIED = "fact_unverified"  # Facts could not be verified
    CITATIONS_STRIPPED = "citations_stripped"  # Invalid citations removed
    ERROR = "error"  # Error during processing


@dataclass
class Correction:
    """
    A single term correction.

    Represents one detected outdated or incorrect legal term.
    """

    original_term: str  # The original (incorrect) term
    corrected_term: str  # The corrected term
    correction_type: str  # Type of correction (outdated, deprecated, etc.)
    confidence: float  # Confidence score of correction (0-1)


@dataclass
class GuardrailResult:
    """
    Result of applying jail warden corrections to a response.

    Contains corrected text, applied corrections, and status.
    """

    corrected_text: str  # The corrected response text
    original_text: str  # The original text before corrections
    corrections: List[Correction]  # List of applied corrections
    status: WardenStatus  # Final warden status
    evidence_level: str  # Evidence level (HIGH/LOW/NONE)
    confidence_score: float  # Overall confidence in the corrections (0-1)


class HarmCategory(str, Enum):
    WEAPONS_EXPLOSIVES = "weapons_explosives"
    DRUG_MANUFACTURING = "drug_manufacturing"
    VIOLENCE_THREATS = "violence_threats"
    SELF_HARM = "self_harm"
    FRAUD_FINANCIAL = "fraud_financial"
    CHILD_EXPLOITATION = "child_exploitation"


class HarmAction(str, Enum):
    BLOCK = "block"
    COMPASSIONATE = "compassionate"
    PASS = "pass"


@dataclass
class HarmDetectionResult:
    action: HarmAction
    category: Optional[HarmCategory] = None
    matched_pattern: Optional[str] = None
    response_message: Optional[str] = None
    legal_whitelist_matched: bool = False


class GuardrailService(BaseService):
    """
    Jail Warden v2 - Post-processing for legal term corrections.

    Features:
    - Term correction (outdated Swedish legal terms)
    - Citation validation
    - Evidence level determination
    - Security violation detection
    - Harmful content detection
    - Output leakage sanitization
    - Confidence scoring for corrections
    """

    # Swedish legal term corrections (outdated → current)
    TERM_CORRECTIONS = {
        # Data protection
        "datainspektionen": {
            "corrected": "Integritetsskyddsmyndigheten (IMY)",
            "type": "outdated_agency",
            "confidence": 0.95,
        },
        "personuppgiftslagen": {
            "corrected": "GDPR och Dataskyddslagen (2018:218)",
            "type": "repealed",
            "confidence": 0.98,
        },
        "pul": {
            "corrected": "GDPR och Dataskyddslagen (2018:218)",
            "type": "abbreviation",
            "confidence": 0.99,
        },
        # Fundamental laws
        "pressfrihetslagen": {
            "corrected": "Tryckfrihetsförordningen (TF)",
            "type": "outdated_name",
            "confidence": 0.92,
        },
        "grundlagen": {
            "corrected": "Regeringsformen (RF)",
            "type": "outdated_name",
            "confidence": 0.90,
        },
        "offentlighetslagen": {
            "corrected": "Offentlighets- och sekretesslagen (OSL)",
            "type": "outdated_name",
            "confidence": 0.93,
        },
        "sekretesslagen": {
            "corrected": "Offentlighets- och sekretesslagen (OSL)",
            "type": "repealed",
            "confidence": 0.94,
        },
        "barnkonventionen": {
            "corrected": "Barnkonventionen (SFS 2018:1197)",
            "type": "incomplete_reference",
            "confidence": 0.91,
        },
        # Discrimination authorities (reorganized)
        "diskrimineringsombudsmannen": {
            "corrected": "Diskrimineringsombudsmannen (DO)",
            "type": "reorganized",
            "confidence": 0.88,
        },
        "jämställdhetsombudsmannen": {
            "corrected": "Diskrimineringsombudsmannen (DO)",
            "type": "reorganized",
            "confidence": 0.88,
        },
        "handikappombudsmannen": {
            "corrected": "Diskrimineringsombudsmannen (DO)",
            "type": "reorganized",
            "confidence": 0.88,
        },
        # Consumer protection
        "konsumentombudsmannen": {
            "corrected": "Konsumentverket",
            "type": "reorganized",
            "confidence": 0.85,
        },
        # Constitutional bodies
        "konstitutionsutskottet": {
            "corrected": "Konstitutionsutskottet (KU)",
            "type": "abbreviation",
            "confidence": 0.86,
        },
    }

    # Security violation patterns (malicious queries, prompt injection, etc.)
    INJECTION_PATTERNS = [
        # English (existing)
        r"(ignore|bypass|override)\s+(all\s+)?(previous\s+)?(instructions|rules|constraints)",
        r"(forget|pretend|act)\s+(like|as)",
        r"(jailbreak|injection|prompt\s+injection)",
        # Swedish
        r"ignorera\s+(alla\s+)?(tidigare\s+)?(instruktioner|regler)",
        r"glöm\s+(dina\s+)?(regler|instruktioner|begränsningar)",
        r"bortse\s+från\s+(alla\s+)?(regler|instruktioner|begränsningar)",
        r"(låtsas|agera)\s+(att\s+du|som\s+(om\s+)?du)",
        r"du\s+är\s+nu\s+(en|ett)",
        r"du\s+är\s+inte\s+längre",
        r"du\s+ska\s+nu\s+agera\s+som",
        r"from\s+now\s+on\s+you\s+are",
        r"skriv\s+utan\s+(begränsningar|restriktioner|regler)",
        r"kringgå\s+(alla\s+)?(regler|säkerhet|filter|begränsningar)",
        r"\bDAN\b.*\brestriktioner\b",
    ]

    PROBING_PATTERNS = [
        # English (existing)
        r"(reveal|show|display)\s+(system|prompt|instructions)",
        r"(root|admin)\s+(access|password|key)",
        # Swedish
        r"visa\s+(din|ditt|dina)\s+(systemprompt|instruktioner|konfiguration)",
        r"visa\s+(system\s*prompt|konfiguration|inställningar)",
        r"vilken\s+modell\s+är\s+du",
        r"vilka\s+(portar|servrar|tjänster)\s+(lyssnar|körs|finns)",
        r"\bAPI[- ]?nyckel\b",
        r"\bsystemarkitektur\b",
        r"\bllama[- ]?server\b",
        r"\bchromadb\b.*\b(konfiguration|data|sökväg)",
        r"\b(backend|server)\s*(port|adress|url|endpoint)",
    ]

    EXECUTION_PATTERNS = [
        # English (existing)
        r"(code|execute|run)\s+(shell|command|script)",
        # Swedish
        r"(kör|exekvera|utför)\s+(kommando|skript|shell|kod)",
    ]

    # Backward compatible combined list
    SECURITY_PATTERNS = INJECTION_PATTERNS + PROBING_PATTERNS + EXECUTION_PATTERNS

    SELF_HARM_PATTERNS = [
        r"jag\s+vill\s+ta\s+livet\s+av\s+mig",
        r"jag\s+vill\s+(inte\s+leva|dö)",
        r"jag\s+orkar\s+inte\s+mer",
        r"(vill|tänker)\s+(begå|ta)\s+självmord",
        r"hur\s+(tar|begår)\s+man\s+självmord",
        r"bästa\s+sättet\s+att\s+(dö|ta\s+livet)",
        r"i\s+want\s+to\s+(kill\s+myself|die|end\s+my\s+life)",
    ]

    CSAM_PATTERNS = [
        r"(sexuell[at]?|pornograf\w*)\s*(bild|material|innehåll)\w*\s*(av|med|på)\s*(barn|minderårig|under\s*årig)",
        r"(barn|minderårig)\w*\s*(pornografi|sexuell[at]?|nakenbilder)",
        r"child\s*(porn|sexual|abuse\s*material)",
    ]

    LEGAL_WHITELIST_PATTERNS = [
        r"vad\s+säger\s+(lagen|.*lagen|.*förordningen|.*balken)\s+om",
        r"vad\s+är\s+(straffet|påföljden)\s+för",
        r"vilka\s+(regler|krav)\s+gäller\s+för",
        r"enligt\s+\d+\s+kap\.?\s+\d+\s*§",
        r"\bSFS\s+\d{4}:\d+",
        r"är\s+det\s+(olagligt|straffbart|tillåtet)\s+att",
        r"\b(narkotikastrafflagen|vapenlagen|brottsbalken|miljöbalken)\b",
        r"\b(terroristbrottslagen|penningtvättslagen)\b",
    ]

    ACTION_VERB_PATTERNS = [
        r"hur\s+(tillverkar|framställer|gör|skapar|bygger)\s+man",
        r"(beskriv|ge)\s+(mig\s+)?(steg\s+för\s+steg|instruktioner|recept|guide)",
        r"hjälp\s+mig\s+att\s+(tillverka|göra|skapa|bygga)",
        r"lär\s+mig\s+att\s+(tillverka|göra|skapa|bygga)",
        r"(how\s+to|instructions\s+for)\s+(make|build|create|manufacture)",
    ]

    DANGEROUS_TOPIC_PATTERNS = {
        HarmCategory.WEAPONS_EXPLOSIVES: [
            r"\b(bomb|sprängmedel|dynamit|sprängämne|skjutvapen|automatvapen|hemmagjord[a]?\s+vapen)\b",
        ],
        HarmCategory.DRUG_MANUFACTURING: [
            r"\b(metamfetamin|amfetamin|kokain|heroin|fentanyl|mdma|ecstasy)\b",
        ],
        HarmCategory.FRAUD_FINANCIAL: [
            r"\b(penningtvätt|skattefusk|förfalska\s+(pengar|dokument|id|pass))\b",
        ],
    }

    DIRECT_THREAT_PATTERNS = [
        (r"skriv\s+(ett\s+)?hot\s+mot", HarmCategory.VIOLENCE_THREATS),
        (r"(hota|utpressa)\s+(en|ett|någon|person|riksdagsledamot)", HarmCategory.VIOLENCE_THREATS),
        (
            r"(planera|genomföra)\s+(ett\s+)?(terrordåd|terrorattack|attentat)",
            HarmCategory.VIOLENCE_THREATS,
        ),
    ]

    OUTPUT_LEAKAGE_PATTERNS = [
        # Port numbers
        (r"\b(8080|8900|3001|3003|5173|5174|11434)\b", "port_number"),
        # Technology names (case-insensitive handled at compile time)
        (r"\bllama[- ]?server\b", "technology"),
        (r"\bllama\.cpp\b", "technology"),
        (r"\bchromadb\b", "technology"),
        (r"\bollama\b", "technology"),
        (r"\bministral[- ]?3\b", "technology"),
        (r"\bbge[- ]?m3\b", "technology"),
        (r"\bbge[- ]?reranker\b", "technology"),
        (r"\buvicorn\b", "technology"),
        (r"\bfastapi\b", "technology"),
        # Model filenames
        (r"\w+\.gguf\b", "model_file"),
        # File paths
        (r"/home/ai-server\S*", "file_path"),
        (r"/backend/\S*", "file_path"),
        (r"/app/services/\S*", "file_path"),
        # Internal IPs
        (r"192\.168\.\d+\.\d+", "internal_ip"),
        (r"10\.\d+\.\d+\.\d+", "internal_ip"),
        (r"127\.0\.0\.1(:\d+)?", "internal_ip"),
        (r"localhost:\d+", "internal_ip"),
    ]

    SELF_HARM_RESPONSE = (
        "Jag hör att du har det svårt. Du är inte ensam och det finns hjälp att få.\n\n"
        "Kontakta:\n"
        "- Mind Självmordslinjen: Ring 90101 (dygnet runt)\n"
        "- Jourhavande medmänniska: Ring 08-702 16 80\n"
        "- BRIS (för unga under 18): Ring 116 111\n"
        "- 1177 Vårdguiden: Ring 1177\n"
        "- mind.se för mer information\n\n"
        "Du förtjänar stöd och hjälp."
    )

    HARMFUL_CONTENT_BLOCK_MESSAGE = (
        "Jag kan inte hjälpa till med den typen av förfrågan. "
        "Som juridisk AI-assistent kan jag svara på frågor om svensk lagstiftning, "
        "rättspraxis och myndigheters verksamhet. "
        "Omformulera gärna din fråga som en juridisk fråga."
    )

    # Citation validation patterns
    CITATION_PATTERNS = [
        r"\[Källa\s+\d+\]",  # [Källa 1], [Källa 2], etc.
        r"\[Source\s+\d+\]",  # [Source 1], etc.
        r"\[källa\s+\d+\]",  # Swedish version
        r"\[doc\s+\d+\]",  # [doc 1], etc.
    ]

    def __init__(self, config: ConfigService):
        """
        Initialize Guardrail Service.

        Args:
            config: ConfigService for configuration access
        """
        super().__init__(config)
        self._compile_patterns()
        logger.info("Guardrail Service initialized")

    def _compile_patterns(self) -> None:
        """
        Compile regex patterns for better performance.
        Pre-compiles security, citation, harmful content, and leakage patterns.
        """
        self._security_patterns = [re.compile(p, re.IGNORECASE) for p in self.SECURITY_PATTERNS]
        self._citation_patterns = [re.compile(p) for p in self.CITATION_PATTERNS]

        # Compile term correction patterns (case-insensitive)
        self._term_patterns = {}
        for original, correction_data in self.TERM_CORRECTIONS.items():
            pattern = re.compile(r"\b" + re.escape(original) + r"\b", re.IGNORECASE)
            self._term_patterns[original] = {
                "pattern": pattern,
                "corrected": correction_data["corrected"],
                "type": correction_data["type"],
                "confidence": correction_data["confidence"],
            }

        # Compile harmful content patterns
        self._self_harm_patterns = [re.compile(p, re.IGNORECASE) for p in self.SELF_HARM_PATTERNS]
        self._csam_patterns = [re.compile(p, re.IGNORECASE) for p in self.CSAM_PATTERNS]
        self._legal_whitelist_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.LEGAL_WHITELIST_PATTERNS
        ]
        self._action_verb_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.ACTION_VERB_PATTERNS
        ]
        self._dangerous_topic_compiled = {
            cat: [re.compile(p, re.IGNORECASE) for p in patterns]
            for cat, patterns in self.DANGEROUS_TOPIC_PATTERNS.items()
        }

        # Compile output leakage patterns
        self._output_leakage_patterns = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.OUTPUT_LEAKAGE_PATTERNS
        ]

    async def initialize(self) -> None:
        """
        Initialize guardrail service.

        Compiles patterns and validates configuration.
        """
        self._compile_patterns()
        self._mark_initialized()

    async def health_check(self) -> bool:
        """
        Check if guardrail service is healthy.

        Always healthy (no external dependencies).
        """
        return True

    async def close(self) -> None:
        """
        Cleanup resources.

        No resources to clean up.
        """
        self._mark_uninitialized()

    def apply_corrections(self, text: str) -> GuardrailResult:
        """
        Apply jail warden corrections to text.

        Detects outdated legal terms and replaces them with current equivalents.

        Args:
            text: The text to correct

        Returns:
            GuardrailResult with corrected text and applied corrections
        """
        original_text = text
        corrected_text = text
        corrections = []

        # Apply term corrections
        for original, pattern_data in self._term_patterns.items():
            pattern = pattern_data["pattern"]

            # Count occurrences before replacement
            count = len(pattern.findall(corrected_text))

            if count > 0:
                # Replace all occurrences
                corrected_text = pattern.sub(pattern_data["corrected"], corrected_text)

                # Add correction record
                corrections.append(
                    Correction(
                        original_term=original,
                        corrected_term=pattern_data["corrected"],
                        correction_type=pattern_data["type"],
                        confidence=pattern_data["confidence"],
                    )
                )

                if count > 5:
                    self.logger.warning(f"Many outdated terms detected: {original} ({count} times)")

        # Determine status
        if not corrections:
            status = WardenStatus.UNCHANGED
        else:
            status = WardenStatus.TERM_CORRECTED

        # Calculate overall confidence score
        if corrections:
            confidence_scores = [c.confidence for c in corrections]
            confidence_score = sum(confidence_scores) / len(confidence_scores)
        else:
            confidence_score = 1.0  # Perfect if no corrections needed

        # Determine evidence level
        # This is a placeholder - real implementation would analyze sources
        evidence_level = self._determine_evidence_level_from_text(original_text)

        result = GuardrailResult(
            corrected_text=corrected_text,
            original_text=original_text,
            corrections=corrections,
            status=status,
            evidence_level=evidence_level,
            confidence_score=confidence_score,
        )

        if corrections:
            self.logger.info(
                f"Applied {len(corrections)} corrections "
                f"(status: {status}, confidence: {confidence_score:.2f})"
            )

        return result

    def security_event(
        self,
        event_type: str,
        query: str,
        pattern_matched: str,
        client_ip: str | None = None,
    ) -> None:
        """Log structured security event."""
        from datetime import datetime, timezone

        self.logger.warning(
            "SECURITY_EVENT",
            extra={
                "security_event_type": event_type,
                "query_truncated": query[:200],
                "pattern_matched": pattern_matched,
                "client_ip": client_ip or "unknown",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def check_harmful_content(self, query: str) -> HarmDetectionResult:
        """Check query for harmful content. Returns HarmDetectionResult."""
        query_lower = query.lower()

        # Phase 1: Self-harm check → compassionate response
        for pattern in self._self_harm_patterns:
            if pattern.search(query_lower):
                self.security_event("SELF_HARM_DETECTED", query, pattern.pattern)
                return HarmDetectionResult(
                    action=HarmAction.COMPASSIONATE,
                    category=HarmCategory.SELF_HARM,
                    matched_pattern=pattern.pattern,
                    response_message=self.SELF_HARM_RESPONSE,
                )

        # Phase 2: CSAM check → zero-tolerance (no whitelist bypass)
        for pattern in self._csam_patterns:
            if pattern.search(query_lower):
                self.security_event("CSAM_BLOCKED", query, pattern.pattern)
                return HarmDetectionResult(
                    action=HarmAction.BLOCK,
                    category=HarmCategory.CHILD_EXPLOITATION,
                    matched_pattern=pattern.pattern,
                    response_message=self.HARMFUL_CONTENT_BLOCK_MESSAGE,
                )

        # Phase 3: Legal framing whitelist → PASS immediately
        for pattern in self._legal_whitelist_patterns:
            if pattern.search(query_lower):
                return HarmDetectionResult(
                    action=HarmAction.PASS,
                    legal_whitelist_matched=True,
                )

        # Phase 4: Direct threat patterns → BLOCK (no conjunction needed)
        for pattern, category in self.DIRECT_THREAT_PATTERNS:
            compiled = re.compile(pattern, re.IGNORECASE)
            if compiled.search(query_lower):
                self.security_event("HARMFUL_CONTENT_BLOCKED", query, pattern)
                return HarmDetectionResult(
                    action=HarmAction.BLOCK,
                    category=category,
                    matched_pattern=pattern,
                    response_message=self.HARMFUL_CONTENT_BLOCK_MESSAGE,
                )

        # Phase 5: Action-verb + dangerous-topic conjunction
        has_action_verb = any(p.search(query_lower) for p in self._action_verb_patterns)
        if has_action_verb:
            for category, patterns in self._dangerous_topic_compiled.items():
                for pattern in patterns:
                    if pattern.search(query_lower):
                        self.security_event("HARMFUL_CONTENT_BLOCKED", query, pattern.pattern)
                        return HarmDetectionResult(
                            action=HarmAction.BLOCK,
                            category=category,
                            matched_pattern=pattern.pattern,
                            response_message=self.HARMFUL_CONTENT_BLOCK_MESSAGE,
                        )

        return HarmDetectionResult(action=HarmAction.PASS)

    def check_output_leakage(self, response: str) -> Tuple[str, List[str]]:
        """Check and sanitize output for self-referential leakage.
        Returns (sanitized_text, list_of_sanitized_items). Never crashes."""
        try:
            sanitized = response
            removed_items: list[str] = []
            replacement = "[intern information borttagen]"

            for pattern, label in self._output_leakage_patterns:
                matches = pattern.findall(sanitized)
                for match in matches:
                    match_str = match if isinstance(match, str) else match[0]
                    if match_str and match_str not in removed_items:
                        removed_items.append(f"{label}: {match_str}")
                sanitized = pattern.sub(replacement, sanitized)

            if removed_items:
                self.security_event(
                    "OUTPUT_SANITIZED",
                    response[:200],
                    "; ".join(removed_items[:5]),
                )
                self.logger.warning(
                    f"Output leakage detected: {len(removed_items)} items sanitized"
                )

            return sanitized, removed_items
        except Exception as e:
            self.logger.error(f"Output leakage check failed (non-fatal): {e}")
            return response, []

    def check_security_violations(self, text: str) -> Tuple[bool, List[str]]:
        """
        Check text for security violations.

        Looks for prompt injection attempts, jailbreak attempts, etc.

        Args:
            text: The text to check

        Returns:
            Tuple of (has_violation, list_of_detected_violations)
        """
        violations = []

        for pattern in self._security_patterns:
            matches = pattern.findall(text)
            for match in matches:
                violations.append(f"Security pattern detected: {match}")
                self.logger.warning(f"Security violation detected: {match}")

        has_violation = len(violations) > 0

        if has_violation:
            self.security_event(
                "INJECTION_DETECTED",
                text,
                "; ".join(violations[:3]),
            )

        return has_violation, violations

    def validate_citations(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate citation format in text.

        Checks for proper citation markers ([Källa X], etc.).

        Args:
            text: The text to validate

        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []

        # Find all citation markers
        for pattern in self._citation_patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Check for common formatting issues
                # - Missing space after bracket
                # - Brackets not properly closed
                # - Invalid citation numbers
                if not re.search(r"\[Källa\s+\d+\s", match) and not re.search(r"\]\s", match):
                    issues.append(f"Improperly formatted citation: {match}")

        # Check for duplicate citation numbers in same text
        citation_numbers = []
        for pattern in self._citation_patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Extract citation number (e.g., "1" from "[Källa 1]")
                num_match = re.search(r"\d+", match)
                if num_match:
                    num = int(num_match.group())
                    if num in citation_numbers:
                        issues.append(f"Duplicate citation number: {num}")
                    citation_numbers.append(num)

        is_valid = len(issues) == 0

        if not is_valid:
            self.logger.warning(f"Citation validation failed: {len(issues)} issues")

        return is_valid, issues

    def check_query_safety(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a user query is safe to process.

        Args:
            query: The user's query

        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        # Check harmful content FIRST
        harm_result = self.check_harmful_content(query)
        if harm_result.action == HarmAction.COMPASSIONATE:
            return False, f"SELF_HARM_DETECTED:{harm_result.response_message}"
        elif harm_result.action == HarmAction.BLOCK:
            return False, harm_result.response_message

        # Then check injection patterns (existing code)
        has_violations, violations = self.check_security_violations(query)

        if has_violations:
            reason = f"Security violation detected: {'; '.join(violations)}"
            self.security_event("INJECTION_BLOCKED", query, "; ".join(violations[:3]))
            self.logger.error(f"Query safety check failed: {reason}")
            return False, reason

        # Check for excessive length (DoS protection)
        if len(query) > 2000:
            reason = f"Query too long ({len(query)} characters)"
            self.logger.warning(reason)
            return False, reason

        # Check for suspicious patterns (all caps, many special chars)
        if not query:
            return True, None
        all_caps_ratio = sum(1 for c in query if c.isupper()) / len(query)
        special_char_ratio = sum(1 for c in query if not c.isalnum() and c != " ") / len(query)

        if all_caps_ratio > 0.8 and len(query) > 50:
            reason = f"Query appears to be shouting (all caps ratio: {all_caps_ratio:.2f})"
            self.logger.warning(reason)
            return False, reason

        if special_char_ratio > 0.3 and len(query) > 50:
            reason = f"Query has too many special characters (ratio: {special_char_ratio:.2f})"
            self.logger.warning(reason)
            return False, reason

        return True, None

    def determine_evidence_level(self, sources: List[dict], answer: str) -> str:
        """
        Determine evidence level based on source quality.

        HIGH: Multiple high-scoring SFS/prop sources
        MEDIUM: Multiple sources with reasonable quality
        LOW: Some relevant sources but lower scores
        NONE: No relevant sources found

        Args:
            sources: List of source dictionaries with 'score' and 'doc_type'
            answer: Generated answer (for future verification)

        Returns:
            Evidence level string (HIGH/MEDIUM/LOW/NONE)
        """
        if not sources:
            return "NONE"

        # Count high-quality sources (score > 0.55, SFS or prop type)
        high_quality = sum(
            1 for s in sources if s.get("score", 0) > 0.55 and s.get("doc_type") in ["sfs", "prop"]
        )

        # Average score
        avg_score = sum(s.get("score", 0) for s in sources) / len(sources)

        if high_quality >= 2 or avg_score > 0.60:
            return "HIGH"
        elif len(sources) >= 3 or (len(sources) >= 2 and avg_score > 0.45):
            return "MEDIUM"
        elif len(sources) > 0 and avg_score > 0.3:
            return "LOW"
        else:
            return "NONE"

    def _determine_evidence_level_from_text(self, text: str) -> str:
        """
        Simple evidence level determination from text alone.

        Placeholder implementation that analyzes text for citation patterns.

        Args:
            text: The text to analyze

        Returns:
            Evidence level string (HIGH/LOW/NONE)
        """
        # Check for citations
        has_citations = False
        for pattern in self._citation_patterns:
            if pattern.search(text):
                has_citations = True
                break

        if not has_citations:
            return "NONE"

        # Check for citation quality (multiple citations = higher confidence)
        citation_count = sum(1 for pattern in self._citation_patterns if pattern.search(text))

        if citation_count >= 3:
            return "HIGH"
        elif citation_count >= 1:
            return "LOW"
        else:
            return "NONE"

    def validate_response(self, text: str, query: str, mode: str) -> GuardrailResult:
        """
        Validate and correct a response based on query and mode.

        Combines term corrections, security checks, and citation validation.

        Args:
            text: The response text to validate
            query: The original user query (for safety check)
            mode: Response mode (chat/assist/evidence)

        Returns:
            GuardrailResult with corrected text and status

        Raises:
            SecurityViolationError: If query is unsafe
            ValidationError: If validation fails
        """
        # Step 1: Check query safety first
        is_safe, unsafe_reason = self.check_query_safety(query)
        if not is_safe:
            raise SecurityViolationError(f"Query rejected: {unsafe_reason}")

        # Step 2: Apply term corrections
        corrections_result = self.apply_corrections(text)
        corrected_text = corrections_result.corrected_text

        # Step 3: Validate citations (for evidence mode)
        if mode.lower() == "evidence":
            is_valid, citation_issues = self.validate_citations(corrected_text)

            if not is_valid:
                # Add citation issues to corrections list
                for issue in citation_issues:
                    corrections_result.corrections.append(
                        Correction(
                            original_term="[citation_error]",
                            corrected_term="[citation_fixed]",
                            correction_type="citation_validation",
                            confidence=1.0,
                        )
                    )

                self.logger.warning(f"Citation validation issues: {citation_issues}")

        # Step 4: Check for security violations in response (for chat mode)
        has_violations = False  # Initialize for chat mode check
        response_violations = []  # Initialize for chat mode check
        if mode.lower() == "chat":
            has_violations, response_violations = self.check_security_violations(corrected_text)

            if has_violations:
                raise SecurityViolationError(
                    f"Response contains security violations: {'; '.join(response_violations)}"
                )

        # Step 5: Recalculate confidence with citation/validation status
        confidence_score = corrections_result.confidence_score
        if mode.lower() == "evidence":
            # Reduce confidence if citation issues found
            if citation_issues:
                confidence_score *= 0.8

        # Update result
        corrections_result.confidence_score = confidence_score
        corrections_result.evidence_level = self._determine_evidence_level_from_text(corrected_text)

        # Determine final status
        if not corrections_result.corrections:
            final_status = WardenStatus.UNCHANGED
        elif has_violations and mode.lower() == "chat":
            final_status = WardenStatus.ERROR
        else:
            final_status = corrections_result.status

        # Build final result
        result = GuardrailResult(
            corrected_text=corrected_text,
            original_text=text,
            corrections=corrections_result.corrections,
            status=final_status,
            evidence_level=corrections_result.evidence_level,
            confidence_score=confidence_score,
        )

        self.logger.info(
            f"Guardrail validation complete (mode: {mode}, "
            f"status: {final_status}, confidence: {confidence_score:.2f})"
        )

        return result

    def get_correction_summary(self, result: GuardrailResult) -> str:
        """
        Get a human-readable summary of applied corrections.

        Args:
            result: GuardrailResult from apply_corrections or validate_response

        Returns:
            Human-readable summary string
        """
        if not result.corrections:
            return "No corrections needed"

        summary_parts = []
        for correction in result.corrections:
            summary_parts.append(
                f"{correction.original_term} → {correction.corrected_term} "
                f"({correction.correction_type})"
            )

        summary = "; ".join(summary_parts)

        return f"Applied {len(result.corrections)} corrections: {summary}"


# Dependency injection function for FastAPI


@lru_cache()
def get_guardrail_service(config: Optional[ConfigService] = None) -> GuardrailService:
    """
    Get singleton GuardrailService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Cached GuardrailService singleton instance
    """
    if config is None:
        config = get_config_service()

    return GuardrailService(config)
