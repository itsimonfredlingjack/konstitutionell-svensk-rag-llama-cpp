"""
Critic Service - Provides critique and revision of structured JSON responses

This service evaluates structured output quality and can revise responses
based on critic feedback. Used in the critic→revise loop for improved accuracy.

Feature-flagged: CONSTITUTIONAL_CRITIC_ENABLED
"""

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .llm_service import LLMService, get_llm_service
from .retrieval_service import SearchResult

logger = get_logger(__name__)


@dataclass
class CriticResult:
    """Result from critic evaluation"""

    ok: bool
    fel: List[str]
    atgard: str
    latency_ms: float


@dataclass
class CriticReflection:
    """
    Result from self-reflection (Chain of Thought).

    Generated BEFORE answering to ensure constitutional compliance.

    Attributes:
        thought_process: The generated chain of thought
        has_sufficient_evidence: Whether enough evidence exists to answer
        missing_evidence: List of what's missing for a good answer
        citation_plan: Which documents should be cited
        constitutional_compliance: Whether response will follow constitutional rules
        confidence: Confidence in the reflection (0.0-1.0)
        latency_ms: Time taken for reflection
    """

    thought_process: str
    has_sufficient_evidence: bool
    missing_evidence: List[str]
    citation_plan: List[str]
    constitutional_compliance: bool
    confidence: float
    latency_ms: float


class CriticService(BaseService):
    """
    Critic Service - Evaluates and revises structured JSON responses.

    Features:
    - Critique structured JSON for validity and quality
    - Revise responses based on critic feedback
    - Max 2 revision attempts
    - Feature-flagged integration

    Thread Safety:
        - No shared mutable state between coroutines
        - Safe for concurrent requests
    """

    def __init__(self, config: ConfigService, llm_service: Optional[LLMService] = None):
        """
        Initialize Critic Service.

        Args:
            config: ConfigService for configuration access
            llm_service: LLMService for model interactions (for self-reflection)
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)

        # Configuration for self-reflection
        self.reflection_enabled = getattr(config.settings, "crag_enable_self_reflection", False)
        self.reflection_model = getattr(
            config.settings, "crag_grader_model", "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
        )
        self.reflection_timeout = getattr(config.settings, "crag_reflection_timeout", 15.0)

        self.logger.info(f"Critic Service initialized (self-reflection: {self.reflection_enabled})")

    async def initialize(self) -> None:
        """Initialize critic service (no-op for now)"""
        self._mark_initialized()
        self.logger.info("Critic Service initialized")

    async def health_check(self) -> bool:
        """Check if critic service is healthy"""
        return True

    async def close(self) -> None:
        """Cleanup critic service (no resources to close)"""
        self._mark_uninitialized()
        self.logger.info("Critic Service closed")

    async def self_reflection(
        self,
        query: str,
        mode: str,
        sources: List[SearchResult],
    ) -> CriticReflection:
        """
        Generate self-reflection (Chain of Thought) BEFORE answering.

        This is the CRAG Self-Reflection Node that ensures constitutional compliance
        by reflecting on the query and available evidence before generation.

        Args:
            query: User's question
            mode: Response mode (evidence/assist)
            sources: Retrieved and graded sources

        Returns:
            CriticReflection with chain of thought and evidence assessment
        """
        start_time = time.perf_counter()

        try:
            if not self.reflection_enabled:
                # Return empty reflection if not enabled
                return CriticReflection(
                    thought_process="Self-reflection disabled",
                    has_sufficient_evidence=len(sources) > 0,
                    missing_evidence=[],
                    citation_plan=[],
                    constitutional_compliance=True,
                    confidence=1.0,
                    latency_ms=0.0,
                )

            # Build reflection prompt
            prompt = self._build_reflection_prompt(query, mode, sources)

            # Create messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": "Du är en reflekterande AI som följer svenska förvaltningslagens principer. Reflektera noggrant innan du svarar.",
                },
                {"role": "user", "content": prompt},
            ]

            # Generate reflection
            full_response = ""
            async for token, _ in self.llm_service.chat_stream(
                messages=messages,
                config_override={
                    "temperature": 0.1,  # Low temperature for consistent reflection
                    "top_p": 0.9,
                    "num_predict": 512,
                    "model": self.reflection_model,
                },
            ):
                if token:
                    full_response += token

            # Parse reflection response
            reflection = self._parse_reflection_response(full_response, sources)
            reflection.latency_ms = (time.perf_counter() - start_time) * 1000

            self.logger.info(
                f"Self-reflection complete: sufficient_evidence={reflection.has_sufficient_evidence}, "
                f"compliance={reflection.constitutional_compliance}, "
                f"confidence={reflection.confidence:.2f}"
            )

            return reflection

        except Exception as e:
            self.logger.error(f"Self-reflection failed: {e}")
            # Return safe fallback
            return CriticReflection(
                thought_process=f"Reflektion misslyckades: {str(e)[:100]}",
                has_sufficient_evidence=False,
                missing_evidence=["Reflektion kunde inte utföras"],
                citation_plan=[],
                constitutional_compliance=False,
                confidence=0.0,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _build_reflection_prompt(self, query: str, mode: str, sources: List[SearchResult]) -> str:
        """
        Build the self-reflection prompt for Chain of Thought.

        Args:
            query: User's question
            mode: Response mode
            sources: Available sources

        Returns:
            Formatted reflection prompt
        """
        sources_text = "\n".join(
            [
                f"[{i + 1}] {s.title} (score: {s.score:.2f})\n{s.snippet[:200]}..."
                for i, s in enumerate(sources[:5])  # Limit to top 5 sources
            ]
        )

        return f"""REFLEKTERA innan du svarar på följande fråga:

FRÅGA: {query}
SVARLÄGE: {mode.upper()}
TILLGÄNGLIGA KÄLLOR ({len(sources)}):
{sources_text if sources_text else "Inga källor hittades"}

KONSTITUTIONELLA REGLER (Svenska förvaltningslagen):
1. LEGALITET: Använd endast information som stöds av dokumenten
2. TRANSPARENS: Alla påståenden måste ha källhänvisning
3. OBJEKTIVITET: Var neutral, saklig och formell
4. SERVICEKYLDIGHET: Var hjälpsam inom ramen för lagen

REFLEKTIONSFRÅGOR:
1. Vilka dokument är relevanta för frågan? Varför?
2. Finns det tillräckligt stöd i dokumenten för att ge ett rättssäkert svar?
3. Hur ska jag strukturera svaret enligt konstitutionella regler?
4. Vilka källor måste jag citera och hur?
5. Måste jag avslå frågan om underlag saknas?

Returnera endast giltig JSON:
{{
  "thought_process": "Din tankekedja på svenska (max 200 ord)",
  "has_sufficient_evidence": true/false,
  "missing_evidence": ["lista på vad som saknas"],
  "citation_plan": ["vilka dokument som ska citera"],
  "constitutional_compliance": true/false,
  "confidence": 0.0-1.0
}}

EXEMPEL PÅ SVAR:
{{
  "thought_process": "Frågan handlar om GDPR artikel 6. Jag har 3 relevanta dokument som täcker detta. Tillräckligt stöd finns för att svara med källor.",
  "has_sufficient_evidence": true,
  "missing_evidence": [],
  "citation_plan": ["GDPR Article 6", "Dataskyddsförordningen"],
  "constitutional_compliance": true,
  "confidence": 0.9
}}"""

    def _parse_reflection_response(
        self, response: str, sources: List[SearchResult]
    ) -> CriticReflection:
        """
        Parse self-reflection response and create CriticReflection.

        Args:
            response: Raw LLM response
            sources: Available sources for context

        Returns:
            CriticReflection with parsed data
        """
        try:
            # Clean response - extract JSON
            response = response.strip()

            # Find JSON in response
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1

            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")

            json_str = response[start_idx:end_idx]
            parsed = json.loads(json_str)

            # Extract fields with defaults
            thought_process = str(parsed.get("thought_process", "Ingen tankekedja genererad"))
            has_sufficient_evidence = bool(parsed.get("has_sufficient_evidence", False))
            missing_evidence = parsed.get("missing_evidence", [])
            citation_plan = parsed.get("citation_plan", [])
            constitutional_compliance = bool(parsed.get("constitutional_compliance", True))
            confidence = float(parsed.get("confidence", 0.5))

            # Ensure confidence is in valid range
            confidence = max(0.0, min(1.0, confidence))

            # Validate against actual sources
            if not sources and has_sufficient_evidence:
                has_sufficient_evidence = False
                missing_evidence.append("Inga källor tillgängliga")
                constitutional_compliance = False

            return CriticReflection(
                thought_process=thought_process,
                has_sufficient_evidence=has_sufficient_evidence,
                missing_evidence=missing_evidence,
                citation_plan=citation_plan,
                constitutional_compliance=constitutional_compliance,
                confidence=confidence,
                latency_ms=0.0,  # Will be set by caller
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(f"Failed to parse reflection response: {e}")

            # Return conservative fallback
            return CriticReflection(
                thought_process=f"Kunde inte tolka reflektion: {str(e)[:50]}",
                has_sufficient_evidence=len(sources) > 0,
                missing_evidence=["Reflektion misslyckades"],
                citation_plan=[],
                constitutional_compliance=False,
                confidence=0.0,
                latency_ms=0.0,
            )

    async def critique(
        self,
        candidate_json: str,
        mode: str,
        sources_context: Optional[List[Dict]] = None,
    ) -> CriticResult:
        """
        Critique structured JSON response for validity and quality.

        Args:
            candidate_json: JSON response to critique
            mode: Response mode (evidence/assist)
            sources_context: Optional context about retrieved sources

        Returns:
            CriticResult with evaluation
        """
        start_time = time.perf_counter()

        try:
            # Parse JSON for validation
            try:
                parsed = json.loads(candidate_json)
            except json.JSONDecodeError as e:
                return CriticResult(
                    ok=False,
                    fel=[f"Invalid JSON: {str(e)}"],
                    atgard="Return valid JSON following the exact schema",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Validate required fields
            fel = []
            required_fields = ["mode", "saknas_underlag", "svar", "kallor", "fakta_utan_kalla"]

            for field in required_fields:
                if field not in parsed:
                    fel.append(f"Missing required field: {field}")

            if fel:
                return CriticResult(
                    ok=False,
                    fel=fel,
                    atgard=f"Add missing fields: {', '.join(fel)}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Mode-specific validation
            if mode == "evidence":
                # EVIDENCE mode validation
                saknas_underlag = parsed.get("saknas_underlag", False)
                kallor = parsed.get("kallor", [])

                if saknas_underlag:
                    # Refusal case - should have empty sources and proper refusal text
                    if kallor:
                        fel.append("EVIDENCE refusal should have empty 'kallor'")

                    refusal_keywords = ["kan inte besvara", "underlag saknas", "spekulera"]
                    svar = parsed.get("svar", "")
                    if not any(keyword.lower() in svar.lower() for keyword in refusal_keywords):
                        fel.append("EVIDENCE refusal should contain proper refusal language")
                else:
                    # Evidence case - should have sources
                    if not kallor:
                        fel.append("EVIDENCE with evidence should have non-empty 'kallor'")

                    # Validate source format
                    for source in kallor:
                        if not isinstance(source, dict):
                            fel.append("Each source in 'kallor' must be an object")
                            break

                        required_source_fields = ["doc_id", "chunk_id", "citat", "loc"]
                        for field in required_source_fields:
                            if field not in source:
                                fel.append(f"Source missing required field: {field}")

                    # Validate claims without sources
                    fakta_utan_kalla = parsed.get("fakta_utan_kalla", [])
                    if fakta_utan_kalla:
                        fel.append(
                            "EVIDENCE mode should not contain 'fakta_utan_kalla' (use ASSIST mode)"
                        )

            elif mode == "assist":
                # ASSIST mode validation - more permissive
                pass

            # Check for internal notes (security)
            if "arbetsanteckning" in parsed:
                fel.append("Response contains internal notes ('arbetsanteckning')")

            ok = len(fel) == 0
            atgard = (
                "Response is valid" if ok else "Fix identified issues and return corrected JSON"
            )

            return CriticResult(
                ok=ok, fel=fel, atgard=atgard, latency_ms=(time.perf_counter() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"Critic evaluation failed: {e}")
            return CriticResult(
                ok=False,
                fel=[f"Critic evaluation error: {str(e)}"],
                atgard="Try again with valid JSON format",
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

    async def revise(
        self,
        candidate_json: str,
        critic_feedback: CriticResult,
    ) -> str:
        """
        Revise JSON response based on critic feedback.

        Args:
            candidate_json: Original JSON response
            critic_feedback: CriticResult from critique() call

        Returns:
            Revised JSON string
        """
        try:
            parsed = json.loads(candidate_json)

            # Simple revision based on feedback
            # In a real implementation, this would use LLM to revise
            # For now, we handle basic corrections

            if not critic_feedback.ok:
                # Try to fix common issues
                if "Missing required field" in str(critic_feedback.fel):
                    # Add missing fields with defaults
                    if "saknas_underlag" not in parsed:
                        parsed["saknas_underlag"] = False
                    if "fakta_utan_kalla" not in parsed:
                        parsed["fakta_utan_kalla"] = []
                    if "kallor" not in parsed:
                        parsed["kallor"] = []

                # Remove internal notes if present
                if "arbetsanteckning" in parsed:
                    del parsed["arbetsanteckning"]

                # For EVIDENCE refusals, ensure proper format
                if parsed.get("mode") == "EVIDENCE" and parsed.get("saknas_underlag", False):
                    if not parsed.get("kallor"):
                        parsed["kallor"] = []
                    if not parsed.get("fakta_utan_kalla"):
                        parsed["fakta_utan_kalla"] = []

            return json.dumps(parsed, ensure_ascii=False)

        except json.JSONDecodeError:
            # If we can't parse JSON, return empty but valid response
            safe_response = {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": "Could not parse response. Please try again.",
                "kallor": [],
                "fakta_utan_kalla": [],
            }
            return json.dumps(safe_response, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Revision failed: {e}")
            # Return safe fallback
            safe_response = {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": "Response revision failed. Please try again.",
                "kallor": [],
                "fakta_utan_kalla": [],
            }
            return json.dumps(safe_response, ensure_ascii=False)


def get_critic_service(
    config: Optional[ConfigService] = None, llm_service: Optional[LLMService] = None
) -> CriticService:
    """
    Get singleton Critic Service instance.

    Args:
        config: Optional ConfigService (uses default if not provided)
        llm_service: Optional LLMService (uses default if not provided)

    Returns:
        Singleton CriticService instance
    """
    if config is None:
        config = get_config_service()
    if llm_service is None:
        llm_service = get_llm_service(config)

    return CriticService(config, llm_service)
