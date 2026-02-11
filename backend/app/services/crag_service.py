"""
CRAG Service — Corrective RAG pipeline for document grading and self-reflection.

Extracted from orchestrator_service.py (Sprint 2, Task #15).
Handles document relevance grading, query rewriting, and self-reflection
via chain-of-thought before generation.
"""

import time
from dataclasses import dataclass
from typing import Any, List, Optional

from ..utils.logging import get_logger
from .config_service import ConfigService
from .critic_service import CriticService
from .grader_service import GraderService
from .guardrail_service import WardenStatus
from .query_processor_service import ResponseMode
from .rag_models import RAGPipelineMetrics, RAGResult, ResponseTemplates
from .retrieval_service import SearchResult

logger = get_logger(__name__)


@dataclass
class CragResult:
    """Result from CRAG pipeline processing."""

    sources: List[SearchResult]
    grade_ms: float
    grade_count: int
    relevant_count: int
    self_reflection_ms: float
    thought_chain: Optional[str]
    rewrite_count: int
    early_return: bool = False
    result: Optional[RAGResult] = None


async def process_crag_grading(
    *,
    config: ConfigService,
    grader: Optional[GraderService],
    critic: Optional[CriticService],
    question: str,
    search_query: str,
    retrieval_result: Any,
    resolved_mode: ResponseMode,
    reasoning_steps: List[str],
    start_time: float,
    query_classification_ms: float,
    decontextualization_ms: float,
    retrieval_ms: float,
) -> CragResult:
    """
    Process CRAG (Corrective RAG) grading and self-reflection.

    Grades retrieved documents for relevance, filters irrelevant ones,
    and optionally runs self-reflection to check evidence sufficiency.

    Returns:
        CragResult with processed sources and metrics, or early return result
    """
    grade_ms = 0.0
    self_reflection_ms = 0.0
    thought_chain = None
    rewrite_count = 0
    grade_count = 0
    relevant_count = 0
    sources = retrieval_result.results

    if not (config.settings.crag_enabled and grader and resolved_mode != ResponseMode.CHAT):
        return CragResult(
            sources=sources,
            grade_ms=0.0,
            grade_count=0,
            relevant_count=0,
            self_reflection_ms=0.0,
            thought_chain=None,
            rewrite_count=0,
        )

    # Grade documents for relevance
    if retrieval_result.results:
        grading_result = await grader.grade_documents(
            query=search_query, documents=retrieval_result.results
        )

        grade_ms = grading_result.metrics.total_latency_ms
        grade_count = grading_result.metrics.total_documents
        relevant_count = grading_result.metrics.relevant_count

        reasoning_steps.append(
            f"CRAG graded {grade_count} documents, {relevant_count} relevant "
            f"({grading_result.metrics.relevant_percentage:.1f}%) in {grade_ms:.1f}ms"
        )

        # Filter sources to only relevant ones
        if relevant_count > 0:
            filtered_docs = [
                doc
                for doc, grade in zip(retrieval_result.results, grading_result.grades)
                if grade.relevant
            ]
            sources = filtered_docs
            reasoning_steps.append(
                f"CRAG filtered to {len(sources)} relevant documents for generation"
            )
        else:
            sources = []
            reasoning_steps.append("CRAG: No relevant documents found, considering query rewrite")
    else:
        grade_count = 0
        relevant_count = 0
        sources = []

    # Early return when EVIDENCE mode has no relevant sources after grading
    if not sources and resolved_mode == ResponseMode.EVIDENCE:
        reasoning_steps.append(
            "CRAG: No relevant documents, EVIDENCE mode requires sources - early return"
        )
        total_ms = (time.perf_counter() - start_time) * 1000
        metrics = RAGPipelineMetrics(
            query_classification_ms=query_classification_ms,
            decontextualization_ms=decontextualization_ms,
            retrieval_ms=retrieval_ms,
            grade_ms=grade_ms,
            self_reflection_ms=0.0,
            total_pipeline_ms=total_ms,
            mode=resolved_mode.value,
            sources_count=0,
            tokens_generated=0,
            corrections_count=0,
            retrieval_strategy=retrieval_result.metrics.strategy,
            retrieval_results_count=len(retrieval_result.results),
            top_relevance_score=retrieval_result.metrics.top_score,
            guardrail_status="unchanged",
            evidence_level="NONE",
            model_used="",
            llm_latency_ms=0.0,
            parse_errors=False,
            structured_output_enabled=config.structured_output_effective_enabled,
            critic_revision_count=0,
            critic_ms=0.0,
            critic_ok=False,
            crag_enabled=True,
            grade_count=grade_count,
            relevant_count=0,
            self_reflection_used=False,
            rewrite_count=0,
        )

        return CragResult(
            sources=[],
            grade_ms=grade_ms,
            grade_count=grade_count,
            relevant_count=0,
            self_reflection_ms=0.0,
            thought_chain=None,
            rewrite_count=0,
            early_return=True,
            result=RAGResult(
                answer=ResponseTemplates.EVIDENCE_REFUSAL,
                sources=[],
                reasoning_steps=reasoning_steps,
                metrics=metrics,
                mode=resolved_mode,
                guardrail_status=WardenStatus.UNCHANGED,
                evidence_level="NONE",
                success=True,
            ),
        )

    # Self-Reflection (Chain of Thought) before generation
    if sources and config.settings.crag_enable_self_reflection and critic:
        reflection_start = time.perf_counter()

        try:
            reflection = await critic.self_reflection(
                query=question, mode=resolved_mode.value, sources=sources
            )

            self_reflection_ms = (time.perf_counter() - reflection_start) * 1000
            thought_chain = reflection.thought_process

            reasoning_steps.append(
                f"Self-reflection generated in {self_reflection_ms:.1f}ms "
                f"(confidence: {reflection.confidence:.2f})"
            )

            # Check if reflection indicates insufficient evidence
            if not reflection.has_sufficient_evidence and resolved_mode == ResponseMode.EVIDENCE:
                refusal_template = getattr(
                    config.settings,
                    "evidence_refusal_template",
                    ResponseTemplates.EVIDENCE_REFUSAL,
                )

                reasoning_steps.append(
                    f"CRAG refusal: insufficient evidence - {', '.join(reflection.missing_evidence)}"
                )

                total_pipeline_ms = (time.perf_counter() - start_time) * 1000
                metrics = RAGPipelineMetrics(
                    query_classification_ms=query_classification_ms,
                    decontextualization_ms=decontextualization_ms,
                    retrieval_ms=retrieval_ms,
                    grade_ms=grade_ms,
                    self_reflection_ms=self_reflection_ms,
                    total_pipeline_ms=total_pipeline_ms,
                    mode=resolved_mode.value,
                    sources_count=0,
                    tokens_generated=0,
                    corrections_count=0,
                    retrieval_strategy=retrieval_result.metrics.strategy,
                    retrieval_results_count=len(retrieval_result.results),
                    top_relevance_score=retrieval_result.metrics.top_score,
                    guardrail_status="unchanged",
                    evidence_level="NONE",
                    model_used="",
                    llm_latency_ms=0.0,
                    parse_errors=False,
                    structured_output_enabled=config.structured_output_effective_enabled,
                    critic_revision_count=0,
                    critic_ms=0.0,
                    critic_ok=False,
                    crag_enabled=True,
                    grade_count=grade_count,
                    relevant_count=relevant_count,
                    self_reflection_used=True,
                    rewrite_count=rewrite_count,
                )

                return CragResult(
                    sources=[],
                    grade_ms=grade_ms,
                    grade_count=grade_count,
                    relevant_count=relevant_count,
                    self_reflection_ms=self_reflection_ms,
                    thought_chain=thought_chain,
                    rewrite_count=rewrite_count,
                    early_return=True,
                    result=RAGResult(
                        answer=refusal_template,
                        sources=[],
                        reasoning_steps=reasoning_steps,
                        metrics=metrics,
                        mode=resolved_mode,
                        guardrail_status=WardenStatus.UNCHANGED,
                        evidence_level="NONE",
                        success=True,
                        thought_chain=thought_chain,
                    ),
                )

        except Exception as e:
            logger.warning(f"Self-reflection failed: {e}")
            reasoning_steps.append(f"Self-reflection failed: {str(e)[:100]}")
            self_reflection_ms = (time.perf_counter() - reflection_start) * 1000

    return CragResult(
        sources=sources,
        grade_ms=grade_ms,
        grade_count=grade_count,
        relevant_count=relevant_count,
        self_reflection_ms=self_reflection_ms,
        thought_chain=thought_chain,
        rewrite_count=rewrite_count,
    )
