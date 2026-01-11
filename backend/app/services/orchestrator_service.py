"""
Orchestrator Service - High-Level RAG Orchestration
The "Brain" that binds together all services for the complete RAG pipeline
"""

import asyncio
import json
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..core.exceptions import SecurityViolationError
from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .critic_service import CriticService, get_critic_service
from .embedding_service import get_embedding_service
from .grader_service import GraderService, get_grader_service
from .graph_service import build_graph, GraphState
from .guardrail_service import GuardrailService, WardenStatus, get_guardrail_service
from .llm_service import LLMService, get_llm_service
from .query_processor_service import (
    QueryProcessorService,
    ResponseMode,
    get_query_processor_service,
)
from .reranking_service import RerankingService, get_reranking_service
from .retrieval_service import (
    RetrievalService,
    RetrievalStrategy,
    SearchResult,
    get_retrieval_service,
)
from .structured_output_service import (
    StructuredOutputSchema,
    StructuredOutputService,
    get_structured_output_service,
)

logger = get_logger(__name__)


# Constants for refusal templates and fallbacks
class ResponseTemplates:
    """Constants for response templates to avoid magic strings."""

    EVIDENCE_REFUSAL = (
        "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen. "
        "Underlag saknas för att ge ett rättssäkert svar, och jag kan därför inte spekulera. "
        "Om du vill kan du omformulera frågan eller ange vilka dokument/avsnitt du vill att jag ska söker i."
    )

    SAFE_FALLBACK = "Jag kunde inte tolka modellens strukturerade svar. Försök igen."

    STRUCTURED_OUTPUT_RETRY_INSTRUCTION = (
        "Du returnerade ogiltig JSON. Returnera endast giltig JSON enligt schema, "
        "inga backticks, ingen extra text."
    )


@dataclass
class RAGPipelineMetrics:
    """
    Metrics for the complete RAG pipeline.
    """

    # Timing
    query_classification_ms: float = 0.0
    decontextualization_ms: float = 0.0
    retrieval_ms: float = 0.0
    llm_generation_ms: float = 0.0
    guardrail_ms: float = 0.0
    reranking_ms: float = 0.0
    total_pipeline_ms: float = 0.0

    # Component results
    mode: str = "assist"
    sources_count: int = 0
    tokens_generated: int = 0
    corrections_count: int = 0

    # Retrieval details
    retrieval_strategy: str = "parallel_v1"
    retrieval_results_count: int = 0
    top_relevance_score: float = 0.0

    # Guardrail details
    guardrail_status: str = "unchanged"
    evidence_level: str = "NONE"

    # LLM details
    model_used: str = ""
    llm_latency_ms: float = 0.0
    tokens_per_second: float = 0.0

    # Structured Output details (NEW)
    structured_output_ms: float = 0.0
    parse_errors: bool = False
    saknas_underlag: Optional[bool] = None
    kallor_count: int = 0
    structured_output_enabled: bool = False

    # Critic→Revise details (NEW)
    critic_revision_count: int = 0
    critic_ms: float = 0.0
    critic_ok: bool = False

    # CRAG (Corrective RAG) details (NEW)
    crag_enabled: bool = False
    grade_count: int = 0
    relevant_count: int = 0
    grade_ms: float = 0.0
    self_reflection_used: bool = False
    self_reflection_ms: float = 0.0
    rewrite_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
            "pipeline": {
                "classification_ms": round(self.query_classification_ms, 2),
                "decontextualization_ms": round(self.decontextualization_ms, 2),
                "retrieval_ms": round(self.retrieval_ms, 2),
                "llm_generation_ms": round(self.llm_generation_ms, 2),
                "guardrail_ms": round(self.guardrail_ms, 2),
                "reranking_ms": round(self.reranking_ms, 2),
                "total_ms": round(self.total_pipeline_ms, 2),
            },
            "retrieval": {
                "strategy": self.retrieval_strategy,
                "results_count": self.retrieval_results_count,
                "top_relevance_score": round(self.top_relevance_score, 4),
            },
            "guardrail": {
                "status": self.guardrail_status,
                "evidence_level": self.evidence_level,
                "corrections_count": self.corrections_count,
            },
            "llm": {
                "model": self.model_used,
                "latency_ms": round(self.llm_latency_ms, 2),
                "tokens_per_second": round(self.tokens_per_second, 2),
            },
        }


@dataclass
class RAGResult:
    """
    Complete result from RAG pipeline.

    Contains the final answer, sources, and full metrics.
    """

    answer: str
    sources: List[SearchResult]
    reasoning_steps: List[str]
    metrics: RAGPipelineMetrics
    mode: ResponseMode
    guardrail_status: WardenStatus
    evidence_level: str
    success: bool = True
    error: Optional[str] = None
    thought_chain: Optional[str] = None  # Chain of Thought from self-reflection

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "answer": self.answer,
            "sources": [
                {
                    "id": s.id,
                    "title": s.title,
                    "snippet": s.snippet,
                    "score": s.score,
                    "source": s.source,
                    "doc_type": s.doc_type,
                    "date": s.date,
                }
                for s in self.sources
            ],
            "reasoning_steps": self.reasoning_steps,
            "metrics": self.metrics.to_dict(),
            "mode": self.mode.value,
            "guardrail_status": self.guardrail_status.value,
            "evidence_level": self.evidence_level,
            "success": self.success,
            "error": self.error,
        }

        # Only include thought_chain if debug mode is enabled
        if self.thought_chain and self.mode.value in ["assist", "evidence"]:
            result["thought_chain"] = self.thought_chain

        return result


class OrchestratorService(BaseService):
    """
    Orchestrator Service - The "Brain" that binds together all RAG components.

    Orchestrates:
    1. Query classification (CHAT/ASSIST/EVIDENCE)
    2. Query decontextualization (from conversation history)
    3. Document retrieval (Phase 1-4 RetrievalOrchestrator)
    4. LLM generation (Ministral 3 14B)
    5. Guardrail validation (Jail Warden v2)
    6. Optional reranking (BGE cross-encoder)

    Thread Safety:
        - All services are singletons
        - No shared mutable state between coroutines
    """

    def __init__(
        self,
        config: ConfigService,
        llm_service: Optional[LLMService] = None,
        query_processor: Optional[QueryProcessorService] = None,
        guardrail: Optional[GuardrailService] = None,
        retrieval: Optional[RetrievalService] = None,
        reranker: Optional[RerankingService] = None,
        structured_output: Optional[StructuredOutputService] = None,  # NEW
        critic: Optional[CriticService] = None,  # NEW
        grader: Optional[GraderService] = None,  # NEW
    ):
        """
        Initialize Orchestrator Service.

        Args:
            config: ConfigService for configuration
            llm_service: LLMService (optional, will create if not provided)
            query_processor: QueryProcessorService (optional, will create if not provided)
            guardrail: GuardrailService (optional, will create if not provided)
            retrieval: RetrievalService (optional, will create if not provided)
            reranker: RerankingService (optional, will create if not provided)
            structured_output: StructuredOutputService (optional, will create if not provided)  # NEW
            critic: CriticService (optional, will create if not provided)  # NEW
            grader: GraderService (optional, will create if not provided)  # NEW
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)
        self.query_processor = query_processor or get_query_processor_service(config)
        self.guardrail = guardrail or get_guardrail_service(config)
        self.retrieval = retrieval or get_retrieval_service(config)
        self.reranker = reranker or get_reranking_service(config)
        self.structured_output = structured_output or get_structured_output_service(config)  # NEW
        # Only create critic service if explicitly provided (for backwards compatibility)
        self.critic = critic or get_critic_service(config, llm_service)
        # Only create grader service if explicitly provided (for backwards compatibility)
        self.grader = grader or get_grader_service(config)

        # Initialize LangGraph agentic flow (lazy initialization)
        self.agent_app = None

        critic_status = "ENABLED" if config.critic_revise_effective_enabled else "DISABLED"
        grader_status = "ENABLED" if config.settings.crag_enabled else "DISABLED"
        self.logger.info(
            f"Orchestrator Service initialized (RAG pipeline ready with structured output, critic→revise: {critic_status}, CRAG grading: {grader_status})"
        )

    async def initialize(self) -> None:
        """
        Initialize all child services.
        """
        # Initialize all services
        await self.llm_service.initialize()
        await self.query_processor.initialize()
        await self.guardrail.initialize()
        await self.retrieval.initialize()
        if self.reranker:
            await self.reranker.initialize()
        await self.structured_output.initialize()  # NEW
        if self.critic:
            await self.critic.initialize()  # NEW
        if self.grader:
            await self.grader.initialize()  # NEW

        self._mark_initialized()
        logger.info("Orchestrator Service initialized (all child services ready)")

    async def run_agentic_flow(
        self,
        question: str,
        mode: Optional[str] = "auto",
    ) -> RAGResult:
        """
        Run query through LangGraph agentic flow.

        Uses the state machine architecture with loops for self-correction.
        This is the new agentic approach replacing the linear pipeline.

        Args:
            question: User's question
            mode: Response mode (auto/chat/assist/evidence)

        Returns:
            RAGResult with answer and metrics
        """
        start_time = time.perf_counter()
        reasoning_steps: List[str] = []

        self.logger.info(
            f"🚀 OrchestratorService: Running Agentic Flow for query: '{question[:50]}...'"
        )

        try:
            # Initialize graph if needed
            if self.agent_app is None:
                self.agent_app = build_graph()
                self.logger.info("LangGraph agentic flow initialized")

            # Classify query to determine mode
            classification = self.query_processor.classify_query(question)
            resolved_mode = self._resolve_query_mode(mode, classification.mode)

            if resolved_mode == ResponseMode.CHAT:
                # CHAT mode: Direct LLM response (no graph)
                messages = [
                    {
                        "role": "system",
                        "content": "Avslappnad AI-assistent. Svara kort på svenska.",
                    },
                    {"role": "user", "content": question},
                ]

                full_answer = ""
                async for token, stats in self.llm_service.chat_stream(
                    messages=messages,
                    config_override={"temperature": 0.7, "num_predict": 512},
                ):
                    if token:
                        full_answer += token

                return RAGResult(
                    answer=full_answer,
                    sources=[],
                    reasoning_steps=["CHAT mode: Direct response"],
                    metrics=RAGPipelineMetrics(
                        total_pipeline_ms=(time.perf_counter() - start_time) * 1000,
                        mode="chat",
                    ),
                    mode=resolved_mode,
                    guardrail_status=WardenStatus.UNCHANGED,
                    evidence_level="NONE",
                )

            # Initialize graph state
            initial_state: GraphState = {
                "question": question,
                "documents": [],
                "generation": "",
                "web_search": False,
                "loop_count": 0,
                "retrieval_loop_count": 0,
                "constitutional_feedback": "",
            }

            reasoning_steps.append(f"Starting agentic flow with mode={resolved_mode.value}")

            self.logger.info(
                f"📊 Graph State initialized: question='{question[:50]}...', mode={resolved_mode.value}"
            )

            # Run graph
            self.logger.info("🔄 Executing LangGraph state machine...")
            final_state = await self.agent_app.ainvoke(initial_state)
            self.logger.info(
                f"✅ Graph execution complete: loop_count={final_state.get('loop_count', 0)}, retrieval_loops={final_state.get('retrieval_loop_count', 0)}"
            )

            # Extract results
            final_answer = final_state.get("generation", "")
            constitutional_feedback = final_state.get("constitutional_feedback", "")
            loop_count = final_state.get("loop_count", 0)
            retrieval_loop_count = final_state.get("retrieval_loop_count", 0)

            # Convert documents back to SearchResult format
            documents = final_state.get("documents", [])
            sources = []
            for doc in documents:
                metadata = doc.metadata or {}
                sources.append(
                    SearchResult(
                        id=metadata.get("id", "unknown"),
                        title=metadata.get("title", "Untitled"),
                        snippet=doc.page_content,
                        score=metadata.get("score", 0.0),
                        source=metadata.get("source", "unknown"),
                        doc_type=metadata.get("doc_type"),
                        date=metadata.get("date"),
                        retriever=metadata.get("retriever", "graph"),
                    )
                )

            reasoning_steps.append(
                f"Agentic flow complete: loops={loop_count}, retrieval_loops={retrieval_loop_count}"
            )
            if constitutional_feedback:
                reasoning_steps.append(
                    f"Constitutional feedback: {constitutional_feedback[:100]}..."
                )

            # Apply guardrail
            guardrail_result = self.guardrail.validate_response(
                text=final_answer,
                query=question,
                mode=resolved_mode.value,
            )

            corrected_answer = (
                guardrail_result.corrected_text if guardrail_result.corrections else final_answer
            )

            return RAGResult(
                answer=corrected_answer,
                sources=sources,
                reasoning_steps=reasoning_steps,
                metrics=RAGPipelineMetrics(
                    total_pipeline_ms=(time.perf_counter() - start_time) * 1000,
                    mode=resolved_mode.value,
                    sources_count=len(sources),
                    corrections_count=len(guardrail_result.corrections)
                    if guardrail_result.corrections
                    else 0,
                    guardrail_status=guardrail_result.status.value,
                ),
                mode=resolved_mode,
                guardrail_status=guardrail_result.status,
                evidence_level="HIGH" if sources else "NONE",
            )

        except Exception as e:
            self.logger.error(f"Agentic flow failed: {e}")
            return RAGResult(
                answer="Ett fel uppstod vid bearbetning av din fråga. Försök igen.",
                sources=[],
                reasoning_steps=reasoning_steps + [f"Error: {str(e)}"],
                metrics=RAGPipelineMetrics(
                    total_pipeline_ms=(time.perf_counter() - start_time) * 1000,
                    mode="error",
                ),
                mode=ResponseMode.ASSIST,
                guardrail_status=WardenStatus.UNCHANGED,
                evidence_level="NONE",
                success=False,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """
        Check if orchestrator and all child services are healthy.

        Returns:
            True if all services healthy, False otherwise
        """
        tasks = [
            self.llm_service.health_check(),
            self.query_processor.health_check(),
            self.guardrail.health_check(),
            self.retrieval.health_check(),
        ]
        if self.reranker:
            tasks.append(self.reranker.health_check())
        if self.critic:
            tasks.append(self.critic.health_check())
        if self.grader:
            tasks.append(self.grader.health_check())

        health_checks = await asyncio.gather(*tasks, return_exceptions=True)

        all_healthy = all(h for h in health_checks if h)

        logger.info(f"Orchestrator health check: {'OK' if all_healthy else 'DEGRADED'}")
        return all_healthy

    async def close(self) -> None:
        """
        Cleanup all child services.
        """
        # Close all services
        await self.llm_service.close()
        # Query processor and guardrail have no resources to close
        await self.retrieval.close()
        if self.reranker:
            await self.reranker.close()
        await self.structured_output.close()  # NEW
        if self.critic:
            await self.critic.close()  # NEW
        if self.grader:
            await self.grader.close()  # NEW

        self._mark_uninitialized()

    async def process_query(
        self,
        question: str,
        mode: Optional[str] = "auto",
        k: int = 10,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        history: Optional[List[dict]] = None,
        enable_reranking: bool = True,
        enable_adaptive: bool = True,
        use_agent: bool = False,  # NEW: Flag to use agentic flow
    ) -> RAGResult:
        """
        Execute full RAG pipeline.

        Pipeline:
        1. Classify query mode (CHAT/ASSIST/EVIDENCE)
        2. Decontextualize query if history provided
        3. Retrieve documents (parallel, rewrite, fusion, or adaptive)
        4. Generate LLM response
        5. Apply guardrail corrections
        6. Optional reranking of results

        Args:
            question: User's question
            mode: Response mode (auto/chat/assist/evidence)
            k: Number of documents to retrieve
            retrieval_strategy: Retrieval strategy (parallel_v1, rewrite_v1, rag_fusion, adaptive)
            history: Conversation history for decontextualization
            enable_reranking: Whether to use BGE reranking
            enable_adaptive: Whether to use adaptive retrieval
            use_agent: If True, use LangGraph agentic flow instead of linear pipeline

        Returns:
            RAGResult with answer, sources, metrics, etc.
        """
        # NEW: Route to agentic flow if flag is set
        if use_agent:
            self.logger.info("Using agentic LangGraph flow")
            return await self.run_agentic_flow(question=question, mode=mode)

        # Original linear pipeline
        start_time = time.perf_counter()
        reasoning_steps = []

        # CRAG variables (initialized for metrics)
        grade_count = 0
        relevant_count = 0
        grade_ms = 0.0
        self_reflection_ms = 0.0
        thought_chain = None
        rewrite_count = 0

        try:
            # STEP 1: Query classification
            class_start = time.perf_counter()
            classification = self.query_processor.classify_query(question)
            resolved_mode = self._resolve_query_mode(mode, classification.mode)
            mode = resolved_mode

            query_classification_ms = (time.perf_counter() - class_start) * 1000
            reasoning_steps.append(
                f"Query classified as {resolved_mode.value} ({classification.reason})"
            )

            # CHAT mode: Skip RAG, just chat
            if resolved_mode == ResponseMode.CHAT:
                return await self._process_chat_mode(question, start_time, reasoning_steps)

            # STEP 2: Decontextualization (if history provided)
            decont_start = time.perf_counter()
            if history:
                decont_result = self.query_processor.decontextualize_query(question, history)
                search_query = decont_result.rewritten_query
                reasoning_steps.append(
                    f"Query decontextualized: '{decont_result.original_query}' → '{decont_result.rewritten_query}' (confidence: {decont_result.confidence:.2f})"
                )
            else:
                search_query = question
                reasoning_steps.append("No history provided, using original query")

            decontextualization_ms = (time.perf_counter() - decont_start) * 1000

            # Convert history to strings for retrieval service
            history_for_retrieval = None
            if history:
                history_for_retrieval = [
                    f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history
                ]

            # STEP 3: Retrieval
            retrieval_start = time.perf_counter()

            # Use adaptive retrieval if enabled
            if enable_adaptive:
                retrieval_strategy = RetrievalStrategy.ADAPTIVE

            retrieval_result = await self.retrieval.search(
                query=search_query,
                k=k,
                strategy=retrieval_strategy,
                history=history_for_retrieval,
            )

            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
            reasoning_steps.append(
                f"Retrieved {len(retrieval_result.results)} documents in {retrieval_ms:.1f}ms (strategy: {retrieval_result.metrics.strategy})"
            )

            if not retrieval_result.success:
                raise Exception(f"Retrieval failed: {retrieval_result.error}")

            # Initialize sources from retrieval result
            sources = retrieval_result.results

            # STEP 3.5: CRAG (Corrective RAG) - Document Grading and Self-Reflection
            crag_result = await self._process_crag_grading(
                question=question,
                search_query=search_query,
                retrieval_result=retrieval_result,
                resolved_mode=resolved_mode,
                reasoning_steps=reasoning_steps,
                start_time=start_time,
                query_classification_ms=query_classification_ms,
                decontextualization_ms=decontextualization_ms,
                retrieval_ms=retrieval_ms,
            )

            # Early return if CRAG determined insufficient evidence
            if crag_result.early_return:
                return crag_result.result

            # Extract CRAG results
            sources = crag_result.sources
            grade_ms = crag_result.grade_ms
            grade_count = crag_result.grade_count
            relevant_count = crag_result.relevant_count
            self_reflection_ms = crag_result.self_reflection_ms
            thought_chain = crag_result.thought_chain
            rewrite_count = crag_result.rewrite_count

            # STEP 4: Build LLM context from sources
            # Note: sources may have been filtered by CRAG already
            if not (
                self.config.settings.crag_enabled
                and self.grader
                and resolved_mode != ResponseMode.CHAT
            ):
                # Only set sources from retrieval if CRAG is not enabled
                sources = retrieval_result.results

            # Extract source text for context
            context_text = self._build_llm_context(sources)
            reasoning_steps.append(f"Built LLM context with {len(sources)} sources")

            # STEP 5: Generate LLM response
            llm_start = time.perf_counter()

            # Get mode-specific configuration
            llm_config = self.query_processor.get_mode_config(resolved_mode.value)

            # RetICL: Retrieve constitutional examples before building prompt
            constitutional_examples = await self._retrieve_constitutional_examples(
                query=question,
                mode=resolved_mode.value,
                k=2,
            )
            examples_text = self._format_constitutional_examples(constitutional_examples)

            # Build messages
            system_prompt = self._build_system_prompt(
                resolved_mode.value,
                sources,
                context_text,
                structured_output_enabled=self.config.structured_output_effective_enabled,
                user_query=question,
            )
            # Replace placeholder with actual examples
            system_prompt = system_prompt.replace("{{CONSTITUTIONAL_EXAMPLES}}", examples_text)
            messages = [
                {"role": "system", "content": system_prompt},
            ]

            # Note: thought_chain is NOT included in prompts for security
            # It can contaminate outputs and leak internal reasoning

            messages.append({"role": "user", "content": f"Fråga: {question}"})

            if history:
                # Add conversation history
                messages.insert(1, *history)  # Insert after system, before current query

            # Stream LLM response
            full_answer = ""
            final_stats = None

            async for token, stats in self.llm_service.chat_stream(
                messages=messages,
                config_override=llm_config,
            ):
                if token:
                    full_answer += token
                else:
                    final_stats = stats

            llm_generation_ms = (time.perf_counter() - llm_start) * 1000
            reasoning_steps.append(
                f"LLM generated {final_stats.tokens_generated if final_stats else 0} tokens in {llm_generation_ms:.1f}ms (model: {final_stats.model_used if final_stats else 'unknown'})"
            )

            # STEP 5.5: Structured Output parsing and validation with retry (NEW)
            structured_output_start = time.perf_counter()
            structured_output_data = None
            parse_errors = False

            if self.config.structured_output_effective_enabled and mode != ResponseMode.CHAT:
                # Helper function for parsing and validation
                def try_parse_and_validate(
                    text: str, attempt_num: int
                ) -> tuple[bool, Optional[StructuredOutputSchema], Optional[str]]:
                    """Parse JSON and validate structured output. Returns (success, validated_schema, error)"""
                    try:
                        json_output = self.structured_output.parse_llm_json(text)
                        is_valid, errors, validated_schema = self.structured_output.validate_output(
                            json_output, mode.value
                        )

                        if is_valid and validated_schema:
                            return True, validated_schema, None
                        else:
                            # Validation failed
                            return (
                                False,
                                None,
                                f"Validation failed attempt {attempt_num}: {', '.join(errors)}",
                            )

                    except json.JSONDecodeError as e:
                        # JSON parsing failed
                        return (
                            False,
                            None,
                            f"JSON parsing failed attempt {attempt_num}: {str(e)[:100]}",
                        )

                # Attempt 1: Normal structured output
                attempt1_success, attempt1_schema, attempt1_error = try_parse_and_validate(
                    full_answer, 1
                )

                if attempt1_success and attempt1_schema:
                    # Success on first attempt
                    structured_output_data = self.structured_output.strip_internal_note(
                        attempt1_schema
                    )
                    reasoning_steps.append("Structured output validation: PASSED (attempt 1)")
                else:
                    # First attempt failed - always try attempt 2
                    parse_errors = True
                    reasoning_steps.append(
                        f"Structured output validation: FAILED attempt 1 ({attempt1_error})"
                    )
                    self.logger.warning(f"Structured output attempt 1 failed: {attempt1_error}")

                    # Attempt 2: Retry with explicit JSON instruction
                    try:
                        retry_instruction = ResponseTemplates.STRUCTURED_OUTPUT_RETRY_INSTRUCTION

                        # Re-run LLM with retry instruction
                        retry_messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Fråga: {question}"},
                            {
                                "role": "assistant",
                                "content": "Försökte att returnera JSON men misslyckades.",
                            },
                            {"role": "user", "content": retry_instruction},
                        ]

                        retry_full_answer = ""
                        async for token, _ in self.llm_service.chat_stream(
                            messages=retry_messages,
                            config_override=llm_config,
                        ):
                            retry_full_answer += token

                        # Parse and validate retry attempt
                        attempt2_success, attempt2_schema, attempt2_error = try_parse_and_validate(
                            retry_full_answer, 2
                        )

                        if attempt2_success and attempt2_schema:
                            # Success on retry attempt
                            structured_output_data = self.structured_output.strip_internal_note(
                                attempt2_schema
                            )
                            reasoning_steps.append(
                                "Structured output validation: PASSED (attempt 2 - retry)"
                            )
                        else:
                            # Both attempts failed - final fallback based on mode
                            reasoning_steps.append(
                                f"Structured output validation: FAILED attempt 2 ({attempt2_error})"
                            )
                            parse_errors = True

                            # Use extracted method for fallback handling
                            full_answer, structured_output_data = self._create_fallback_response(
                                mode, reasoning_steps
                            )

                    except Exception as retry_e:
                        # Retry attempt also failed
                        parse_errors = True
                        reasoning_steps.append(
                            f"Attempt 2 failed unexpectedly: {str(retry_e)[:100]}"
                        )
                        self.logger.warning(f"Attempt 2 failed unexpectedly: {retry_e}")

                        # Final fallback - use extracted method
                        full_answer, structured_output_data = self._create_fallback_response(
                            mode, reasoning_steps
                        )

            structured_output_ms = (time.perf_counter() - structured_output_start) * 1000

            # Update final answer from structured output if available
            if structured_output_data and "svar" in structured_output_data:
                full_answer = structured_output_data["svar"]

            # STEP 5B: Critic→Revise Loop (feature-flagged)
            critic_revision_count = 0
            critic_ms = 0.0
            critic_feedback = None

            if (
                self.config.critic_revise_effective_enabled
                and self.critic  # Only if critic service is available
                and structured_output_data
                and mode != ResponseMode.CHAT
            ):
                critic_start = time.perf_counter()

                # Convert structured output back to JSON for critique
                current_json = json.dumps(structured_output_data, ensure_ascii=False)

                # Prepare sources context for critique
                sources_context = [
                    {"id": s.id, "title": s.title, "snippet": s.snippet, "score": s.score}
                    for s in sources
                ]

                max_revisions = min(2, getattr(self.config.settings, "critic_max_revisions", 2))

                while critic_revision_count < max_revisions:
                    # Critique current response
                    critic_result = await self.critic.critique(
                        candidate_json=current_json,
                        mode=mode.value,
                        sources_context=sources_context,
                    )

                    critic_feedback = critic_result

                    if critic_result.ok:
                        # Success - no more revisions needed
                        break

                    # Not OK - attempt revision
                    if critic_revision_count < max_revisions - 1:
                        # Revise based on feedback
                        revised_json = await self.critic.revise(
                            candidate_json=current_json, critic_feedback=critic_result
                        )

                        # Parse revised JSON to continue loop
                        try:
                            revised_data = json.loads(revised_json)
                            current_json = revised_json
                            structured_output_data = revised_data
                            if "svar" in revised_data:
                                full_answer = revised_data["svar"]

                            critic_revision_count += 1
                        except json.JSONDecodeError:
                            # Revision failed, break loop
                            break
                    else:
                        # Last revision attempt failed
                        critic_revision_count += 1
                        break

                critic_ms = (time.perf_counter() - critic_start) * 1000

                # Log critic metrics (minimal logging as specified)
                self.logger.info(
                    f"Critic: mode={mode.value}, "
                    f"revisions={critic_revision_count}, "
                    f"ok={critic_feedback.ok if critic_feedback else False}, "
                    f"latency_ms={critic_ms:.1f}"
                )

                # BLOCKER FIX: Enforce mode-specific fallback when critic still fails after max revisions
                if (
                    critic_feedback
                    and not critic_feedback.ok
                    and critic_revision_count >= max_revisions
                ):
                    if mode == ResponseMode.EVIDENCE:
                        # EVIDENCE: Force refusal template
                        refusal_text = getattr(
                            self.config.settings,
                            "evidence_refusal_template",
                            "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
                        )
                        structured_output_data = {
                            "mode": "EVIDENCE",
                            "saknas_underlag": True,
                            "svar": refusal_text,
                            "kallor": [],
                            "fakta_utan_kalla": [],
                        }
                        full_answer = refusal_text
                        sources = []  # Clear sources for refusal
                    else:
                        # ASSIST: Force safe fallback (no sources, no fake citations)
                        safe_fallback = (
                            "Jag kunde inte tolka modellens strukturerade svar. Försök igen."
                        )
                        full_answer = safe_fallback
                        structured_output_data = {
                            "mode": "ASSIST",
                            "saknas_underlag": False,
                            "svar": safe_fallback,
                            "kallor": [],
                            "fakta_utan_kalla": [],
                        }

            # Log structured output metrics (without arbetsanteckning for security)
            if self.config.structured_output_effective_enabled and mode != ResponseMode.CHAT:
                self.logger.info(
                    f"Structured output: mode={mode.value}, "
                    f"parse_errors={parse_errors}, "
                    f"latency_ms={structured_output_ms:.1f}, "
                    f"saknas_underlag={structured_output_data.get('saknas_underlag', False) if structured_output_data else None}, "
                    f"kallor_count={len(structured_output_data.get('kallor', [])) if structured_output_data else 0}"
                )

            # STEP 6: Apply guardrail corrections
            guardrail_start = time.perf_counter()
            guardrail_result = self.guardrail.validate_response(
                text=full_answer,
                query=question,
                mode=mode.value,
            )

            guardrail_ms = (time.perf_counter() - guardrail_start) * 1000
            reasoning_steps.append(
                f"Guardrail corrections: {len(guardrail_result.corrections)} applied (status: {guardrail_result.status})"
            )

            # STEP 7: Optional reranking
            reranking_ms = 0.0
            if enable_reranking and self.reranker and mode != ResponseMode.CHAT:
                rerank_start = time.perf_counter()

                # Rerank sources (not the answer)
                rerank_result = await self.reranker.rerank(
                    query=search_query,
                    documents=[
                        {
                            "id": s.id,
                            "title": s.title,
                            "snippet": s.snippet,
                            "score": s.score,
                        }
                        for s in sources
                    ],
                    top_k=len(sources),
                )

                reranking_ms = (time.perf_counter() - rerank_start) * 1000
                reasoning_steps.append(
                    f"Reranked sources in {reranking_ms:.1f}ms (top score: {rerank_result.reranked_scores[0] if rerank_result.reranked_scores else 0:.4f})"
                )

                # Update sources with reranked order
                sources = [
                    SearchResult(
                        id=r["id"],
                        title=r["title"],
                        snippet=r["snippet"],
                        score=rerank_result.reranked_scores[i],
                        source=sources[i].source,
                        doc_type=sources[i].doc_type,
                        date=sources[i].date,
                        retriever=sources[i].retriever,
                    )
                    for i, r in enumerate(rerank_result.reranked_docs)
                ]

            # Build final result
            final_answer = guardrail_result.corrected_text

            # Determine evidence level
            evidence_level = self.query_processor.determine_evidence_level(
                sources=[{"score": s.score, "doc_type": s.doc_type} for s in sources],
                answer=final_answer,
            )

            # Build metrics
            total_pipeline_ms = (time.perf_counter() - start_time) * 1000

            metrics = RAGPipelineMetrics(
                query_classification_ms=query_classification_ms,
                decontextualization_ms=decontextualization_ms,
                retrieval_ms=retrieval_ms,
                llm_generation_ms=llm_generation_ms,
                guardrail_ms=guardrail_ms,
                reranking_ms=reranking_ms,
                structured_output_ms=structured_output_ms,  # NEW
                total_pipeline_ms=total_pipeline_ms,
                mode=mode.value,
                sources_count=len(sources),
                tokens_generated=final_stats.tokens_generated if final_stats else 0,
                corrections_count=len(guardrail_result.corrections),
                retrieval_strategy=retrieval_result.metrics.strategy,
                retrieval_results_count=len(retrieval_result.results),
                top_relevance_score=retrieval_result.metrics.top_score,
                guardrail_status=guardrail_result.status.value,
                evidence_level=evidence_level,
                model_used=final_stats.model_used if final_stats else "",
                llm_latency_ms=final_stats.total_duration_ms if final_stats else 0.0,
                parse_errors=parse_errors,  # NEW
                saknas_underlag=structured_output_data.get("saknas_underlag")
                if structured_output_data
                else None,  # NEW
                kallor_count=len(structured_output_data.get("kallor", []))
                if structured_output_data
                else 0,  # NEW
                structured_output_enabled=self.config.structured_output_effective_enabled,  # NEW
                tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
                critic_revision_count=critic_revision_count,  # NEW
                critic_ms=0.0 if critic_revision_count == 0 else critic_ms,  # NEW
                critic_ok=critic_feedback.ok if critic_feedback else False,  # NEW
                crag_enabled=self.config.settings.crag_enabled,  # NEW
                grade_count=grade_count,  # NEW
                relevant_count=relevant_count,  # NEW
                grade_ms=grade_ms,  # NEW
                self_reflection_used=bool(thought_chain),  # NEW
                self_reflection_ms=self_reflection_ms,  # NEW
                rewrite_count=rewrite_count,  # NEW
            )

            logger.info(
                f"RAG pipeline complete: {total_pipeline_ms:.1f}ms "
                f"(mode: {mode.value}, sources: {len(sources)}, "
                f"tokens: {final_stats.tokens_generated if final_stats else 0})"
            )

            return RAGResult(
                answer=final_answer,
                sources=sources,
                reasoning_steps=reasoning_steps,
                metrics=metrics,
                mode=mode,
                guardrail_status=guardrail_result.status,
                evidence_level=evidence_level,
                success=True,
                thought_chain=thought_chain,  # NEW
            )

        except SecurityViolationError as e:
            logger.error(f"Security violation in RAG pipeline: {e}")
            return RAGResult(
                answer="Säkerhetsöverträckelse. Din fråga innehåller otillåten innehåll.",
                sources=[],
                reasoning_steps=[f"Security violation: {str(e)}"],
                metrics=RAGPipelineMetrics(),
                mode=mode if isinstance(mode, ResponseMode) else ResponseMode.ASSIST,
                guardrail_status=WardenStatus.ERROR,
                evidence_level="NONE",
                success=False,
                error=str(e),
                thought_chain=None,  # NEW
            )

        except Exception as e:
            logger.error(f"RAG pipeline failed: {e}")
            return RAGResult(
                answer="Tyvärr uppstod ett fel vid svarandet på din fråga.",
                sources=[],
                reasoning_steps=[f"Error: {str(e)}"],
                metrics=RAGPipelineMetrics(),
                mode=mode if isinstance(mode, ResponseMode) else ResponseMode.ASSIST,
                guardrail_status=WardenStatus.ERROR,
                evidence_level="NONE",
                success=False,
                error=str(e),
                thought_chain=None,  # NEW
            )

    async def _process_chat_mode(
        self,
        question: str,
        start_time: float,
        reasoning_steps: List[str],
    ) -> RAGResult:
        """
        Process query in CHAT mode (no RAG, just chat).

        Bypasses retrieval and guardrails, direct LLM chat.
        """
        # Build chat messages
        system_prompt = """Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # Generate response
        full_answer = ""
        final_stats = None

        async for token, stats in self.llm_service.chat_stream(
            messages=messages,
            config_override={"temperature": 0.7, "num_predict": 512},
        ):
            if token:
                full_answer += token
            else:
                final_stats = stats

        reasoning_steps.append("CHAT mode: Direct LLM response (no RAG)")

        # Build metrics
        total_pipeline_ms = (time.perf_counter() - start_time) * 1000

        metrics = RAGPipelineMetrics(
            total_pipeline_ms=total_pipeline_ms,
            mode="chat",
            tokens_generated=final_stats.tokens_generated if final_stats else 0,
            llm_generation_ms=final_stats.total_duration_ms if final_stats else 0.0,
            model_used=final_stats.model_used if final_stats else "",
            llm_latency_ms=final_stats.total_duration_ms if final_stats else 0.0,
            tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
        )

        return RAGResult(
            answer=full_answer,
            sources=[],
            reasoning_steps=reasoning_steps,
            metrics=metrics,
            mode=ResponseMode.CHAT,
            guardrail_status=WardenStatus.UNCHANGED,
            evidence_level="NONE",
            success=True,
            thought_chain=None,  # NEW
        )

    def _build_llm_context(self, sources: List[SearchResult]) -> str:
        """
        Build LLM context from retrieved sources.

        Formats sources with metadata and relevance scores.
        """
        if not sources:
            return "Inga relevanta källor hittades i korpusen."

        context_parts = []
        for i, source in enumerate(sources, 1):
            doc_type = source.doc_type or "okänt"
            score = source.score
            priority_marker = (
                "⭐ PRIORITET (SFS)" if doc_type == "sfs" else f"Typ: {doc_type.upper()}"
            )

            context_parts.append(
                f"[Källa {i}: {source.title}] {priority_marker} | Relevans: {score:.2f}\n"
                f"{source.snippet}"
            )

        return "\n\n".join(context_parts)

    async def _retrieve_constitutional_examples(
        self, query: str, mode: str, k: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Retrieve constitutional examples for RetICL (Retrieval-Augmented In-Context Learning).

        Searches the 'constitutional_examples' ChromaDB collection for similar examples
        based on the user's query. Returns top-k examples matching the mode.

        Args:
            query: User's question
            mode: Response mode (evidence/assist)
            k: Number of examples to retrieve (default: 2)

        Returns:
            List of example dictionaries with 'user' and 'assistant' fields
        """
        try:
            # Import chromadb here to avoid circular imports
            import chromadb
            import chromadb.config

            # Connect to ChromaDB
            chromadb_path = self.config.chromadb_path
            collection_name = "constitutional_examples"

            client = chromadb.PersistentClient(
                path=chromadb_path,
                settings=chromadb.config.Settings(anonymized_telemetry=False),
            )

            # Get collection
            try:
                collection = client.get_collection(name=collection_name)
            except Exception:
                # Collection doesn't exist yet - return empty list
                self.logger.debug(
                    f"Constitutional examples collection not found: {collection_name}"
                )
                return []

            # Generate embedding for query
            embedding_service = get_embedding_service(self.config)
            query_embedding = embedding_service.embed_single(query)

            # Search for similar examples (filter by mode if possible)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where={"mode": mode.upper()} if mode in ["evidence", "assist"] else None,
            )

            # Parse results
            examples = []
            if results and results.get("metadatas") and len(results["metadatas"]) > 0:
                for metadata in results["metadatas"][0]:
                    try:
                        example_json = json.loads(metadata.get("example_json", "{}"))
                        examples.append(example_json)
                    except (json.JSONDecodeError, KeyError):
                        continue

            self.logger.debug(f"Retrieved {len(examples)} constitutional examples for mode={mode}")
            return examples

        except Exception as e:
            self.logger.warning(f"Failed to retrieve constitutional examples: {e}")
            return []

    def _format_constitutional_examples(self, examples: List[Dict[str, Any]]) -> str:
        """
        Format constitutional examples for inclusion in system prompt.

        Args:
            examples: List of example dictionaries

        Returns:
            Formatted string with examples
        """
        if not examples:
            return ""

        formatted_parts = []
        for i, example in enumerate(examples, 1):
            user = example.get("user", "")
            assistant = example.get("assistant", {})
            assistant_json = json.dumps(assistant, ensure_ascii=False, indent=2)

            formatted_parts.append(
                f"Exempel {i}:\n" f"Användare: {user}\n" f"Assistent: {assistant_json}\n"
            )

        return (
            "\n"
            + "=" * 60
            + "\nKONSTITUTIONELLA EXEMPEL (Följ dessa som mallar för ton och format):\n"
            + "=" * 60
            + "\n"
            + "\n".join(formatted_parts)
            + "\n"
            + "=" * 60
            + "\n"
        )

    def _build_system_prompt(
        self,
        mode: str,
        sources: List[SearchResult],
        context_text: str,
        structured_output_enabled: bool = True,
        user_query: Optional[str] = None,
    ) -> str:
        """
        Build system prompt based on response mode and structured output setting.

        Different prompts for CHAT/ASSIST/EVIDENCE modes.
        JSON schema instructions only included when structured_output_enabled=True.
        Includes RetICL examples if available.
        """

        # Base prompt templates
        base_evidence = """Du är en AI-assistent inom en svensk myndighet. Din uppgift är att besvara användarens fråga enbart utifrån tillgängliga dokument och källor. KONSTITUTIONELLA REGLER: 1. Legalitet: Du får INTE använda information som inte uttryckligen stöds av de dokument som hämtats. 2. Transparens: Alla påståenden måste ha en källhänvisning. Om en uppgift saknas i dokumenten, svara ärligt att underlag saknas. Spekulera aldrig. 3. Objektivitet: Var neutral, saklig och formell. Undvik värdeladdade ord. Svara på svenska."""

        base_assist = """Du är en AI-assistent inom en svensk myndighet. Du ska vara hjälpsam och pedagogisk i enlighet med serviceskyldigheten i förvaltningslagen. KONSTITUTIONELLA REGLER: 1. Pedagogik: Du får använda din allmänna kunskap för att förklara begrepp och sammanhang. 2. Källkritik: Du måste tydligt skilja på vad som är verifierade fakta från dokument (ange källa) och vad som är dina egna förklaringar. 3. Tonalitet: Var artig och tillgänglig, men behåll en professionell myndighetston. Svara på svenska."""

        # JSON schema instruction (only when structured output is enabled)
        json_instruction = """
Du måste svara i strikt JSON enligt detta schema:
{{
  "mode": "EVIDENCE" | "ASSIST",
  "saknas_underlag": boolean,
  "svar": string,
  "kallor": [{{"doc_id": string, "chunk_id": string, "citat": string, "loc": string}}],
  "fakta_utan_kalla": [string],
  "arbetsanteckning": string
}}

Regler:
- I EVIDENCE: "fakta_utan_kalla" måste vara tom. Om du saknar stöd: sätt "saknas_underlag": true och skriv refusal-svar i "svar".
- I ASSIST: Fakta från dokument ska ha källa. Allmän kunskap ska inte få en låtsaskälla; skriv då i "fakta_utan_kalla" kort vad som är allmän förklaring.
- "arbetsanteckning" får bara vara en mycket kort kontrollnotis. Den kommer inte visas för användaren."""

        # Text instruction (when structured output is disabled)
        text_instruction = """
Om du saknar stöd för svaret i dokumenten, svara tydligt att du saknar underlag för att ge ett rättssäkert svar. Spekulera aldrig. Var neutral, saklig och formell. Svara kortfattat på svenska."""

        # RetICL: Retrieve constitutional examples (async, but we'll handle it synchronously for now)
        # Note: This is a synchronous method, so we'll need to make it async or use a workaround
        constitutional_examples_text = ""
        if user_query and mode in ["evidence", "assist"]:
            # For now, we'll retrieve examples in the calling method and pass them
            # This method signature will be updated to accept examples as parameter
            pass

        if mode == "evidence":
            prompt = base_evidence
            if structured_output_enabled:
                prompt += json_instruction
            else:
                prompt += text_instruction
            # Add RetICL examples placeholder (will be replaced by caller)
            prompt += "{{CONSTITUTIONAL_EXAMPLES}}"
            prompt += f"\n\nKälla från korpusen:\n{context_text}"
            return prompt

        elif mode == "assist":
            prompt = base_assist
            if structured_output_enabled:
                prompt += json_instruction
            else:
                prompt += text_instruction
            # Add RetICL examples placeholder (will be replaced by caller)
            prompt += "{{CONSTITUTIONAL_EXAMPLES}}"
            prompt += f"\n\nKälla från korpusen:\n{context_text}"
            return prompt

        else:  # chat
            return """Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat."""

    async def stream_query(
        self,
        question: str,
        mode: Optional[str] = "auto",
        k: int = 10,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        history: Optional[List[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream RAG pipeline with Server-Sent Events.

        Yields SSE-formatted events:
        - metadata: initial metadata and sources
        - token: each token as it's generated
        - corrections: jail warden corrections
        - done: final statistics

        This is the streaming version of process_query().
        """
        start_time = time.perf_counter()

        try:
            # Step 1: Classify query
            classification = self.query_processor.classify_query(question)

            # Normalize mode safely (None/str/Enum) - use extracted method
            response_mode = self._resolve_query_mode(mode, classification.mode)

            if response_mode == ResponseMode.CHAT:
                # CHAT mode: Direct streaming
                yield f"data: {self._json({'type': 'metadata', 'mode': 'chat'})}\n\n"

                async for token, _ in self.llm_service.chat_stream(
                    messages=[
                        {
                            "role": "system",
                            "content": "Avslappnad AI-assistent. Svara kort på svenska.",
                        },
                        {"role": "user", "content": question},
                    ],
                    config_override={"temperature": 0.7, "num_predict": 512},
                ):
                    yield f"data: {self._json({'type': 'token', 'content': token})}\n\n"

                yield f"data: {self._json({'type': 'done'})}\n\n"
                return

            # ASSIST/EVIDENCE: Full RAG pipeline
            # Step 2: Decontextualization
            if history:
                decont_result = self.query_processor.decontextualize_query(question, history)
                search_query = decont_result.rewritten_query
                yield f"data: {self._json({'type': 'decontextualized', 'original': question, 'rewritten': search_query})}\n\n"
            else:
                search_query = question

            # Step 3: Retrieval
            retrieval_start = time.perf_counter()

            # Convert history to strings for retrieval service - optimized: filter empty content
            history_for_retrieval = None
            if history:
                history_for_retrieval = [
                    f"{h.get('role', 'user')}: {h.get('content', '')}"
                    for h in history
                    if h.get("content")  # Filter empty content for better performance
                ]

            retrieval_result = await self.retrieval.search(
                query=search_query,
                k=k,
                strategy=retrieval_strategy,
                history=history_for_retrieval,
            )

            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

            # CRAG: Document Grading & Filtering
            sources = retrieval_result.results

            if self.config.settings.crag_enabled and self.grader:
                # Grade documents
                grading_result = await self.grader.grade_documents(
                    query=search_query, documents=retrieval_result.results
                )

                # Emit grading status event
                yield f"data: {self._json({'type': 'grading', 'total': grading_result.metrics.total_documents, 'relevant': grading_result.metrics.relevant_count, 'message': '⚖️ Väger bevis...'})}\n\n"

                # Filter sources
                relevant_docs = []
                for doc, grade in zip(retrieval_result.results, grading_result.grades):
                    if grade.relevant:
                        relevant_docs.append(doc)

                if relevant_docs:
                    sources = relevant_docs
                else:
                    # If no relevant docs, keep empty list (will trigger refusal if enabled)
                    sources = []

            # CRAG: Self-Reflection
            thought_chain = None
            if (
                sources
                and self.config.settings.crag_enabled
                and self.config.settings.crag_enable_self_reflection
                and self.critic
            ):
                reflection = await self.critic.self_reflection(
                    query=question, mode=response_mode.value, sources=sources
                )
                thought_chain = reflection.thought_process

                # Emit thought chain event
                yield f"data: {self._json({'type': 'thought_chain', 'content': thought_chain})}\n\n"

                # Handle refusal
                if (
                    not reflection.has_sufficient_evidence
                    and response_mode == ResponseMode.EVIDENCE
                ):
                    refusal_text = getattr(
                        self.config.settings,
                        "evidence_refusal_template",
                        "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
                    )
                    refusal_reason = (
                        ", ".join(reflection.missing_evidence)
                        if reflection.missing_evidence
                        else "Underlag saknas"
                    )

                    # Emit metadata with empty sources and refusal reason
                    yield f"data: {self._json({'type': 'metadata', 'mode': response_mode.value, 'sources': [], 'search_time_ms': retrieval_ms, 'refusal': True, 'refusal_reason': refusal_reason})}\n\n"
                    # Emit explicit refusal event
                    yield f"data: {self._json({'type': 'refusal', 'message': refusal_text, 'reason': refusal_reason})}\n\n"
                    # Stream refusal as content
                    yield f"data: {self._json({'type': 'token', 'content': refusal_text})}\n\n"
                    yield f"data: {self._json({'type': 'done'})}\n\n"
                    return

            # Build sources for metadata event
            sources_metadata = [
                {
                    "id": s.id,
                    "title": s.title,
                    "score": s.score,
                    "doc_type": s.doc_type,
                    "source": s.source,
                }
                for s in sources
            ]

            yield f"data: {self._json({'type': 'metadata', 'mode': response_mode.value, 'sources': sources_metadata, 'search_time_ms': retrieval_ms})}\n\n"

            # Step 4: Build context and stream LLM response
            context_text = self._build_llm_context(sources)

            # RetICL: Retrieve constitutional examples before building prompt
            constitutional_examples = await self._retrieve_constitutional_examples(
                query=question,
                mode=response_mode.value,
                k=2,
            )
            examples_text = self._format_constitutional_examples(constitutional_examples)

            # Disable structured output for streaming to prevent internal note leakage
            system_prompt = self._build_system_prompt(
                response_mode.value,
                sources,
                context_text,
                structured_output_enabled=False,
                user_query=question,
            )
            # Replace placeholder with actual examples
            system_prompt = system_prompt.replace("{{CONSTITUTIONAL_EXAMPLES}}", examples_text)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Fråga: {question}"},
            ]

            if history:
                messages.insert(1, *history)

            # Stream LLM tokens
            full_answer = ""

            async for token, stats in self.llm_service.chat_stream(
                messages=messages,
                config_override=self.query_processor.get_mode_config(response_mode.value),
            ):
                if token:
                    full_answer += token
                    yield f"data: {self._json({'type': 'token', 'content': token})}\n\n"

            # Step 5: Guardrail corrections
            guardrail_result = self.guardrail.validate_response(
                text=full_answer,
                query=question,
                mode=response_mode.value,
            )

            if guardrail_result.corrections:
                # Send correction event
                yield f"data: {self._json({'type': 'corrections', 'corrections': [c.original_term + ' → ' + c.corrected_term for c in guardrail_result.corrections], 'corrected_text': guardrail_result.corrected_text})}\n\n"

            # Final done event
            total_ms = (time.perf_counter() - start_time) * 1000

            yield f"data: {self._json({'type': 'done', 'total_time_ms': total_ms})}\n\n"

        except Exception as e:
            yield f"data: {self._json({'type': 'error', 'message': str(e)})}\n\n"

    def _resolve_query_mode(self, mode: Optional[str], default_mode: ResponseMode) -> ResponseMode:
        """
        Resolve query mode from various input types.

        Args:
            mode: Mode as None, str, or ResponseMode enum
            default_mode: Default mode from classification

        Returns:
            Resolved ResponseMode enum
        """
        if mode is None:
            return default_mode
        elif isinstance(mode, ResponseMode):
            return mode
        elif isinstance(mode, str):
            if mode != "auto":
                try:
                    return ResponseMode(mode)
                except ValueError:
                    return default_mode
            return default_mode
        else:
            return default_mode

    def _create_fallback_response(
        self, mode: ResponseMode, reasoning_steps: List[str]
    ) -> tuple[str, dict]:
        """
        Create fallback response when structured output parsing fails.

        Args:
            mode: Response mode (EVIDENCE or ASSIST)
            reasoning_steps: List to append reasoning steps

        Returns:
            Tuple of (answer_text, structured_output_data)
        """
        if mode == ResponseMode.EVIDENCE:
            refusal_template = ResponseTemplates.EVIDENCE_REFUSAL
            reasoning_steps.append("EVIDENCE both attempts failed - using refusal template")
            return refusal_template, {
                "mode": "EVIDENCE",
                "saknas_underlag": True,
                "svar": refusal_template,
                "kallor": [],
                "fakta_utan_kalla": [],
            }
        else:
            safe_fallback = ResponseTemplates.SAFE_FALLBACK
            reasoning_steps.append("ASSIST both attempts failed - using safe fallback")
            return safe_fallback, {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": safe_fallback,
                "kallor": [],
                "fakta_utan_kalla": [],
            }

    async def _process_crag_grading(
        self,
        question: str,
        search_query: str,
        retrieval_result: Any,
        resolved_mode: ResponseMode,
        reasoning_steps: List[str],
        start_time: float,
        query_classification_ms: float,
        decontextualization_ms: float,
        retrieval_ms: float,
    ) -> "CragResult":
        """
        Process CRAG (Corrective RAG) grading and self-reflection.

        Returns:
            CragResult with processed sources and metrics, or early return result
        """
        from dataclasses import dataclass
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            pass

        @dataclass
        class CragResult:
            sources: List[SearchResult]
            grade_ms: float
            grade_count: int
            relevant_count: int
            self_reflection_ms: float
            thought_chain: Optional[str]
            rewrite_count: int
            early_return: bool = False
            result: Optional[RAGResult] = None

        grade_ms = 0.0
        self_reflection_ms = 0.0
        thought_chain = None
        rewrite_count = 0
        grade_count = 0
        relevant_count = 0
        sources = retrieval_result.results

        if not (
            self.config.settings.crag_enabled and self.grader and resolved_mode != ResponseMode.CHAT
        ):
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
            grading_result = await self.grader.grade_documents(
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
                reasoning_steps.append(
                    "CRAG: No relevant documents found, considering query rewrite"
                )
        else:
            grade_count = 0
            relevant_count = 0
            sources = []

        # Self-Reflection (Chain of Thought) before generation
        if sources and self.config.settings.crag_enable_self_reflection and self.critic:
            reflection_start = time.perf_counter()

            try:
                reflection = await self.critic.self_reflection(
                    query=question, mode=resolved_mode.value, sources=sources
                )

                self_reflection_ms = (time.perf_counter() - reflection_start) * 1000
                thought_chain = reflection.thought_process

                reasoning_steps.append(
                    f"Self-reflection generated in {self_reflection_ms:.1f}ms "
                    f"(confidence: {reflection.confidence:.2f})"
                )

                # Check if reflection indicates insufficient evidence
                if (
                    not reflection.has_sufficient_evidence
                    and resolved_mode == ResponseMode.EVIDENCE
                ):
                    refusal_template = getattr(
                        self.config.settings,
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
                        structured_output_enabled=self.config.structured_output_effective_enabled,
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
                self.logger.warning(f"Self-reflection failed: {e}")
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

    def _json(self, data: dict) -> str:
        """Helper to format SSE event data"""
        import json

        return json.dumps(data)

    def get_status(self) -> dict:
        """
        Get orchestrator status with child service status.

        Returns:
            Dictionary with orchestrator and child service health
        """
        return {
            "orchestrator": "initialized" if self.is_initialized else "uninitialized",
            "llm_service": "initialized" if self.llm_service.is_initialized else "uninitialized",
            "query_processor": "initialized"
            if self.query_processor.is_initialized
            else "uninitialized",
            "guardrail": "initialized" if self.guardrail.is_initialized else "uninitialized",
            "retrieval": "initialized" if self.retrieval.is_initialized else "uninitialized",
            "reranker": "initialized"
            if self.reranker and self.reranker.is_initialized
            else "not_available",
        }


# Dependency injection function for FastAPI
@lru_cache()
def get_orchestrator_service(
    config=None,
    llm_service=None,
    query_processor=None,
    guardrail=None,
    retrieval=None,
    reranker=None,
    structured_output=None,  # NEW
) -> OrchestratorService:
    """
    Get singleton OrchestratorService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)
        llm_service: Optional LLMService (optional, will create if not provided)
        query_processor: Optional QueryProcessorService (optional, will create if not provided)
        guardrail: Optional GuardrailService (optional, will create if not provided)
        retrieval: Optional RetrievalService (typical, will create if not provided)
        reranker: Optional RerankingService (optional, will create if not provided)

    Returns:
        Cached OrchestratorService instance
    """
    if config is None:
        config = get_config_service()

    return OrchestratorService(
        config=config,
        llm_service=llm_service,
        query_processor=query_processor,
        guardrail=guardrail,
        retrieval=retrieval,
        reranker=reranker,
        structured_output=structured_output,  # NEW
    )
