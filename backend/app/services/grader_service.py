"""
Grader Service - Document Relevance Assessment for CRAG
Uses primary LLM (Ministral-3-14B) to grade retrieved documents

CRAG Component: Grade Node
Purpose: Filter out irrelevant documents before generation to prevent
         context pollution and improve answer quality
"""

import asyncio
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .llm_service import LLMService, get_llm_service
from .retrieval_service import SearchResult

logger = get_logger(__name__)

# GBNF grammar: forces canonical output {"relevance":"yes"} or {"relevance":"no"}
GRADING_GRAMMAR = 'root ::= "{" "\\"relevance\\"" ":" value "}"\nvalue ::= "\\"yes\\"" | "\\"no\\""'


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
    - Uses primary LLM (Ministral-3-14B) for relevance assessment
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
            config.settings, "crag_grader_model", "Ministral-3-14B-Instruct-2512-Q4_K_M.gguf"
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

                    # Process results (gather preserves order)
                    for doc, result in zip(batch_docs, batch_results):
                        if isinstance(result, Exception):
                            self.logger.warning(f"Grading failed for {doc.id}: {result}")
                            # Create fallback grade with actual doc ID
                            grade_result = GradeResult(
                                doc_id=doc.id,
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

                    # Add timeout placeholders with actual doc IDs
                    for doc in batch_docs:
                        grade_result = GradeResult(
                            doc_id=doc.id,
                            relevant=False,
                            reason=f"Timeout grading document {doc.id}",
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
                    "num_predict": 32,  # Minimal JSON is ~20 tokens
                    "grammar": GRADING_GRAMMAR,
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
        return f"""Är detta dokument relevant för frågan? Svara ENDAST med JSON.

FRÅGA: {query}

DOKUMENT: {document.title} ({document.doc_type or "okänd"})
{document.snippet[:500]}

Relevant = dokumentet besvarar eller direkt relaterar till frågan.
Irrelevant = dokumentet handlar om något annat.

Svara med EXAKT ett av dessa:
{{"relevance":"yes"}}
{{"relevance":"no"}}"""

    def _parse_grading_response(self, doc_id: str, response: str, threshold: float) -> GradeResult:
        """
        Parse minimal JSON grading response: {"relevance":"yes"} or {"relevance":"no"}.

        Falls back to keyword detection if JSON parsing fails.
        The threshold parameter is unused with binary grading but kept for API compat.
        """
        try:
            cleaned = response.strip()

            start_idx = cleaned.find("{")
            end_idx = cleaned.rfind("}") + 1

            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")

            parsed = json.loads(cleaned[start_idx:end_idx])

            # Support both new minimal format and legacy format
            relevance_val = parsed.get("relevance", parsed.get("relevant", "no"))
            if isinstance(relevance_val, bool):
                relevant = relevance_val
            else:
                relevant = str(relevance_val).lower().strip() in ("yes", "true")

            score = 1.0 if relevant else 0.0
            reason = parsed.get("reason", "yes" if relevant else "no")

            return GradeResult(
                doc_id=doc_id,
                relevant=relevant,
                reason=reason,
                score=score,
                confidence=1.0 if relevant else 0.8,
                latency_ms=0.0,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Fallback: keyword detection in raw response
            lower = response.lower()
            relevant = (
                '"yes"' in lower or '"relevant": true' in lower or '"relevance":"yes"' in lower
            )

            self.logger.warning(
                f"JSON parse failed for {doc_id}, keyword fallback → {relevant}: {e}"
            )

            return GradeResult(
                doc_id=doc_id,
                relevant=relevant,
                reason=f"Keyword fallback: {str(e)[:50]}",
                score=1.0 if relevant else 0.0,
                confidence=0.5,
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
