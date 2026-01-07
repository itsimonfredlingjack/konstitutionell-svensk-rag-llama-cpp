"""
Grader Service - Document Relevance Assessment for CRAG
Uses lightweight LLM (Qwen 0.5B) to grade retrieved documents

CRAG Component: Grade Node
Purpose: Filter out irrelevant documents before generation to prevent
         context pollution and improve answer quality
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from functools import lru_cache
import json
import time
import asyncio

from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .retrieval_service import SearchResult
from .llm_service import LLMService, get_llm_service
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GradeResult:
    """
    Result from document grading operation.

    Attributes:
        doc_id: Document identifier from retrieval
        relevant: True if document is relevant to query
        reason: Human-readable explanation of relevance assessment
        score: Numerical score 0.0-1.0 (confidence of relevance)
        confidence: Confidence in the grading decision (0.0-1.0)
        latency_ms: Time taken for grading this document
    """

    doc_id: str
    relevant: bool
    reason: str
    score: float
    confidence: float
    latency_ms: float


@dataclass
class GradingMetrics:
    """
    Metrics for document grading operation.

    Attributes:
        total_documents: Total documents graded
        relevant_count: Number of relevant documents found
        relevant_percentage: Percentage of relevant documents
        avg_score: Average relevance score
        total_latency_ms: Total time for grading
        per_doc_latency_ms: Average latency per document
    """

    total_documents: int
    relevant_count: int
    relevant_percentage: float
    avg_score: float
    total_latency_ms: float
    per_doc_latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "total_documents": self.total_documents,
            "relevant_count": self.relevant_count,
            "relevant_percentage": round(self.relevant_percentage, 2),
            "avg_score": round(self.avg_score, 3),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "per_doc_latency_ms": round(self.per_doc_latency_ms, 2),
        }


@dataclass
class GradingResult:
    """
    Complete result from document grading operation.

    Attributes:
        grades: List of individual document grade results
        metrics: Grading performance metrics
        success: Whether grading completed successfully
        error: Error message if grading failed
    """

    grades: List[GradeResult]
    metrics: GradingMetrics
    success: bool = True
    error: Optional[str] = None


class GraderService(BaseService):
    """
    Grader Service - Document Relevance Assessment for CRAG.

    Features:
    - Uses lightweight LLM (Qwen 0.5B) for fast relevance assessment
    - Parallel grading of multiple documents
    - Configurable relevance threshold
    - Timeout protection and error handling
    - Confidence scoring for decision quality

    Thread Safety:
        - Async concurrent processing
        - No shared mutable state between coroutines
        - Safe for concurrent requests
    """

    def __init__(
        self,
        config: ConfigService,
        llm_service: Optional[LLMService] = None,
    ):
        """
        Initialize Grader Service.

        Args:
            config: ConfigService for configuration access
            llm_service: LLMService for model interactions
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)

        # Configuration
        self.grade_threshold = getattr(config.settings, "crag_grade_threshold", 0.3)
        self.grader_model = getattr(
            config.settings, "crag_grader_model", "Qwen2.5-0.5B-Instruct-Q5_K_M.gguf"
        )
        self.max_concurrent = getattr(config.settings, "crag_max_concurrent_grading", 5)
        self.grade_timeout = getattr(config.settings, "crag_grade_timeout", 10.0)

        self.logger.info(
            f"Grader Service initialized (threshold: {self.grade_threshold}, "
            f"model: {self.grader_model}, concurrent: {self.max_concurrent})"
        )

    async def initialize(self) -> None:
        """Initialize grader service (LLM service will be initialized separately)"""
        self._mark_initialized()
        logger.info("Grader Service initialized")

    async def health_check(self) -> bool:
        """Check if grader service is healthy"""
        try:
            # Basic health check - can we access configuration?
            is_healthy = (
                self.grade_threshold >= 0.0
                and self.grade_threshold <= 1.0
                and self.max_concurrent > 0
            )

            logger.info(f"Grader Service health check: {'OK' if is_healthy else 'FAILED'}")
            return is_healthy

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self) -> None:
        """Cleanup grader service (no resources to close)"""
        self._mark_uninitialized()
        logger.info("Grader Service closed")

    async def grade_documents(
        self,
        query: str,
        documents: List[SearchResult],
        threshold: Optional[float] = None,
    ) -> GradingResult:
        """
        Grade documents for relevance to the query.

        This is the main CRAG Grade Node functionality.
        Uses lightweight LLM to assess whether each document is relevant
        before proceeding to generation phase.

        Args:
            query: The user's question
            documents: List of retrieved documents to grade
            threshold: Relevance threshold (overrides config if provided)

        Returns:
            GradingResult with grades and metrics

        Raises:
            LLMTimeoutError: If grading times out
            LLMConnectionError: If LLM service unavailable
        """
        start_time = time.perf_counter()

        try:
            if not documents:
                return GradingResult(
                    grades=[],
                    metrics=GradingMetrics(
                        total_documents=0,
                        relevant_count=0,
                        relevant_percentage=0.0,
                        avg_score=0.0,
                        total_latency_ms=0.0,
                        per_doc_latency_ms=0.0,
                    ),
                    success=True,
                )

            # Use provided threshold or config default
            effective_threshold = self.grade_threshold if threshold is None else threshold

            self.logger.info(f"Grading {len(documents)} documents for query: '{query[:50]}...'")

            # Parallel grading with proper concurrency control
            grades = []
            for i in range(0, len(documents), self.max_concurrent):
                batch_docs = documents[i : i + self.max_concurrent]

                # Create tasks for this batch
                batch_tasks = []
                for doc in batch_docs:
                    task = asyncio.create_task(
                        self._grade_single_document_async(query, doc, effective_threshold)
                    )
                    batch_tasks.append(task)

                try:
                    # Wait for batch with timeout
                    batch_results = await asyncio.wait_for(
                        asyncio.gather(*batch_tasks, return_exceptions=True),
                        timeout=self.grade_timeout,
                    )

                    # Process results
                    for result in batch_results:
                        if isinstance(result, Exception):
                            self.logger.warning(f"Grading failed: {result}")
                            # Create fallback grade
                            grade_result = GradeResult(
                                doc_id="error_doc",
                                relevant=False,
                                reason=f"Grading error: {str(result)[:50]}",
                                score=0.0,
                                confidence=0.0,
                                latency_ms=0.0,
                            )
                            grades.append(grade_result)
                        else:
                            grades.append(result)

                except asyncio.TimeoutError:
                    # Cancel pending tasks and add timeout placeholders
                    for task in batch_tasks:
                        if not task.done():
                            task.cancel()

                    # Add timeout placeholders for the batch
                    for _ in batch_docs:
                        grade_result = GradeResult(
                            doc_id="timeout_doc",
                            relevant=False,
                            reason="Grading timeout - treated as irrelevant",
                            score=0.0,
                            confidence=0.0,
                            latency_ms=self.grade_timeout * 1000,
                        )
                        grades.append(grade_result)

            # Sort grades by original document order
            doc_id_to_index = {doc.id: i for i, doc in enumerate(documents)}
            grades.sort(key=lambda x: doc_id_to_index.get(x.doc_id, 999))

            # Calculate metrics
            total_latency_ms = (time.perf_counter() - start_time) * 1000
            relevant_count = sum(1 for g in grades if g.relevant)
            avg_score = sum(g.score for g in grades) / len(grades)

            metrics = GradingMetrics(
                total_documents=len(documents),
                relevant_count=relevant_count,
                relevant_percentage=(relevant_count / len(documents)) * 100,
                avg_score=avg_score,
                total_latency_ms=total_latency_ms,
                per_doc_latency_ms=total_latency_ms / len(documents),
            )

            self.logger.info(
                f"Grading complete: {relevant_count}/{len(documents)} relevant "
                f"({metrics.relevant_percentage:.1f}%) in {total_latency_ms:.1f}ms"
            )

            return GradingResult(grades=grades, metrics=metrics, success=True)

        except Exception as e:
            logger.error(f"Document grading failed: {e}")
            return GradingResult(
                grades=[],
                metrics=GradingMetrics(
                    total_documents=len(documents),
                    relevant_count=0,
                    relevant_percentage=0.0,
                    avg_score=0.0,
                    total_latency_ms=(time.perf_counter() - start_time) * 1000,
                    per_doc_latency_ms=0.0,
                ),
                success=False,
                error=str(e),
            )

    async def _grade_single_document_async(
        self, query: str, document: SearchResult, threshold: float
    ) -> GradeResult:
        """
        Async wrapper for single document grading.

        This method runs asynchronously for parallel processing.
        """
        doc_start_time = time.perf_counter()

        try:
            # Create grading prompt
            prompt = self._build_grading_prompt(query, document)

            # Create messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": "Du är en dokumentgraderare. Bedöm relevans med hög precision.",
                },
                {"role": "user", "content": prompt},
            ]

            # Generate LLM response
            full_response = ""
            async for token, _ in self.llm_service.chat_stream(
                messages=messages,
                config_override={
                    "temperature": 0.1,  # Low temperature for consistent grading
                    "top_p": 0.9,
                    "num_predict": 256,
                    "model": self.grader_model,
                },
            ):
                if token:
                    full_response += token

            # Parse response
            grade_result = self._parse_grading_response(document.id, full_response, threshold)

            # Calculate latency
            latency_ms = (time.perf_counter() - doc_start_time) * 1000
            grade_result.latency_ms = latency_ms

            return grade_result

        except Exception as e:
            self.logger.error(f"Failed to grade document {document.id}: {e}")
            # Return fallback grade
            return GradeResult(
                doc_id=document.id,
                relevant=False,
                reason=f"Grading failed: {str(e)[:100]}",
                score=0.0,
                confidence=0.0,
                latency_ms=(time.perf_counter() - doc_start_time) * 1000,
            )

    def _build_grading_prompt(self, query: str, document: SearchResult) -> str:
        """
        Build the grading prompt for LLM.

        Args:
            query: User's question
            document: Document to grade

        Returns:
            Formatted prompt string
        """
        return f"""Bedöm om detta dokument är relevant för frågan.

FRÅGA: {query}

DOKUMENT:
Titel: {document.title}
Typ: {document.doc_type or 'Okänd'}
Datum: {document.date or 'Okänt'}
Innehåll: {document.snippet}

KONSTITUTIONELLA REGLER FÖR RELEVANS:
1. EXAKT MATCH: Dokumentet handlar om samma ämne som frågan
2. SEMANTISK RELEVANS: Begrepp och termer överlappar meningsfullt
3. LAGSTIFTNING: Lagtexter och förordningar är relevanta för juridiska frågor
4. AVANCERA: Dokument om personuppgifter är relevanta för GDPR-frågor

BESLUTSKRITERIER:
- Relevant: Dokumentet innehåller information som direkt besvarar eller relaterar till frågan
- Irrelevant: Dokumentet handlar om något helt annat eller saknar koppling till frågan

Returnera endast giltig JSON:
{{
  "relevant": true/false,
  "reason": "Förklaring på svenska varför dokumentet är relevant/irrelevant",
  "score": 0.0-1.0 (konfidens i beslutet)
}}

EXEMPEL PÅ SVAR:
{{"relevant": true, "reason": "Dokumentet handlar om GDPR artikel 6 vilket direkt besvarar frågan om laglig grund", "score": 0.9}}
{{"relevant": false, "reason": "Dokumentet handlar om skattefrågor vilket inte relaterar till frågan om GDPR", "score": 0.1}}"""

    def _parse_grading_response(self, doc_id: str, response: str, threshold: float) -> GradeResult:
        """
        Parse LLM response and create GradeResult.

        Args:
            doc_id: Document identifier
            response: Raw LLM response
            threshold: Relevance threshold

        Returns:
            GradeResult with parsed data
        """
        try:
            # Clean response - extract JSON
            response = response.strip()

            # Find JSON in response (might be wrapped in text)
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1

            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")

            json_str = response[start_idx:end_idx]

            # Parse JSON
            parsed = json.loads(json_str)

            # Extract fields
            relevant = bool(parsed.get("relevant", False))
            reason = str(parsed.get("reason", "Ingen förklaring given"))
            score = float(parsed.get("score", 0.0))

            # Ensure score is in valid range
            score = max(0.0, min(1.0, score))

            # Apply threshold to determine relevance
            final_relevant = relevant and score >= threshold

            # Calculate confidence (higher when score is far from threshold)
            if score >= threshold:
                confidence = min(1.0, (score - threshold) / (1.0 - threshold) + 0.5)
            else:
                confidence = min(1.0, (threshold - score) / threshold + 0.5)

            return GradeResult(
                doc_id=doc_id,
                relevant=final_relevant,
                reason=reason,
                score=score,
                confidence=confidence,
                latency_ms=0.0,  # Will be set by caller
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(
                f"Failed to parse grading response for {doc_id}: {e}. Response: {response[:200]}"
            )

            # Return conservative fallback
            return GradeResult(
                doc_id=doc_id,
                relevant=False,  # Conservative: assume irrelevant if can't parse
                reason=f"Kunde inte tolka bedömning: {str(e)[:50]}",
                score=0.0,
                confidence=0.0,
                latency_ms=0.0,
            )

    async def get_filtered_documents(
        self, query: str, documents: List[SearchResult], threshold: Optional[float] = None
    ) -> tuple[List[SearchResult], GradingResult]:
        """
        Convenience method to get filtered documents with grading result.

        Args:
            query: User's question
            documents: Retrieved documents
            threshold: Relevance threshold

        Returns:
            Tuple of (filtered_documents, grading_result)
        """
        grading_result = await self.grade_documents(query, documents, threshold)

        # Filter documents based on grading
        filtered_docs = []
        for doc, grade in zip(documents, grading_result.grades):
            if grade.relevant:
                filtered_docs.append(doc)

        return filtered_docs, grading_result


# Dependency injection function for FastAPI
@lru_cache()
def get_grader_service(config: Optional[ConfigService] = None) -> GraderService:
    """
    Get singleton GraderService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Singleton GraderService instance
    """
    if config is None:
        config = get_config_service()

    return GraderService(config)


# Global instance for backward compatibility
grader_service = get_grader_service()
