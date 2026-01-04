"""
Orchestrator Service - High-Level RAG Orchestration
The "Brain" that binds together all services for the complete RAG pipeline
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass
import time
import asyncio

from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .llm_service import LLMService, get_llm_service
from .query_processor_service import (
    QueryProcessorService,
    get_query_processor_service,
    ResponseMode,
)
from .guardrail_service import GuardrailService, get_guardrail_service, WardenStatus
from .retrieval_service import (
    RetrievalService,
    get_retrieval_service,
    RetrievalStrategy,
    SearchResult,
)
from .reranking_service import RerankingService, get_reranking_service
from ..core.exceptions import SecurityViolationError
from ..utils.logging import get_logger

logger = get_logger(__name__)


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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        return {
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
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)
        self.query_processor = query_processor or get_query_processor_service(config)
        self.guardrail = guardrail or get_guardrail_service(config)
        self.retrieval = retrieval or get_retrieval_service(config)
        self.reranker = reranker or get_reranking_service(config)

        self.logger.info("Orchestrator Service initialized (RAG pipeline ready)")

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

        self._mark_initialized()
        logger.info("Orchestrator Service initialized (all child services ready)")

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

        Returns:
            RAGResult with answer, sources, metrics, etc.
        """
        start_time = time.perf_counter()
        reasoning_steps = []

        try:
            # STEP 1: Query classification
            class_start = time.perf_counter()
            classification = self.query_processor.classify_query(question)
            # Convert string mode to ResponseMode Enum if needed
            if isinstance(mode, str):
                mode = mode if mode != "auto" else classification.mode
                # Ensure mode is ResponseMode Enum (not just string)
                if isinstance(mode, str):
                    mode = ResponseMode(mode)
            else:
                mode = mode if mode != ResponseMode.AUTO else classification.mode

            query_classification_ms = (time.perf_counter() - class_start) * 1000
            reasoning_steps.append(f"Query classified as {mode.value} ({classification.reason})")

            # CHAT mode: Skip RAG, just chat
            if mode == ResponseMode.CHAT:
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

            # STEP 3: Retrieval
            retrieval_start = time.perf_counter()

            # Use adaptive retrieval if enabled
            if enable_adaptive:
                retrieval_strategy = RetrievalStrategy.ADAPTIVE

            retrieval_result = await self.retrieval.search(
                query=search_query,
                k=k,
                strategy=retrieval_strategy,
                history=history,
            )

            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
            reasoning_steps.append(
                f"Retrieved {len(retrieval_result.results)} documents in {retrieval_ms:.1f}ms (strategy: {retrieval_result.metrics.strategy})"
            )

            if not retrieval_result.success:
                raise Exception(f"Retrieval failed: {retrieval_result.error}")

            # STEP 4: Build LLM context from sources
            sources = retrieval_result.results

            # Extract source text for context
            context_text = self._build_llm_context(sources)
            reasoning_steps.append(f"Built LLM context with {len(sources)} sources")

            # STEP 5: Generate LLM response
            llm_start = time.perf_counter()

            # Get mode-specific configuration
            llm_config = self.query_processor.get_mode_config(mode.value)

            # Build messages
            system_prompt = self._build_system_prompt(mode.value, sources, context_text)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Fråga: {question}"},
            ]

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
                tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
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

    def _build_system_prompt(
        self, mode: str, sources: List[SearchResult], context_text: str
    ) -> str:
        """
        Build system prompt based on response mode.

        Different prompts for CHAT/ASSIST/EVIDENCE modes.
        """
        if mode == "evidence":
            return f"""Du är en juridisk expert specialiserad på svensk lag och förvaltningsrätt.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling) - PRIORITERA DETTA
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT FÖR EVIDENCE-MODE:
1. Använd ENDAST källor från korpusen - hitta på ingenting
2. Citera ALLTID exakta SFS-nummer och paragrafer när de finns i källorna
3. PRIORITERA SFS-källor (lagtext) över prop/sou/bet när flera källor finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt: "Jag saknar specifik information i korpusen"
5. Var formell, exakt och saklig - MAX 200 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Citera källor med [Källa X] och inklud SFS-nummer/paragraf när tillgängligt

Källor från korpusen:
{context_text}"""

        elif mode == "assist":
            return f"""Du är Constitutional AI, en expert på svensk lag och myndighetsförvaltning.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling)
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT:
1. Använd ALLTID källorna som tillhandahålls i kontexten när de finns
2. Citera källor i formatet [Källa X] när du refererar till dem
3. Prioritera SFS-källor (lagtext) över prop/sou när båda finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information
5. Var kortfattat men exakt - MAX 150 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, # - eller formatering
7. Inga rubriker, inga punktlistor, inga asterisker
8. Gå rakt på sak och var hjälpsam

Källor från korpusen:
{context_text}"""

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
            response_mode = mode if mode != "auto" else classification.mode

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
            decont_start = time.perf_counter()
            if history:
                decont_result = self.query_processor.decontextualize_query(question, history)
                search_query = decont_result.rewritten_query
                yield f"data: {self._json({'type': 'decontextualized', 'original': question, 'rewritten': search_query})}\n\n"
            else:
                search_query = question

            decontextualization_ms = (time.perf_counter() - decont_start) * 1000

            # Step 3: Retrieval
            retrieval_start = time.perf_counter()
            retrieval_result = await self.retrieval.search(
                query=search_query,
                k=k,
                strategy=retrieval_strategy,
                history=history,
            )

            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

            # Build sources for metadata event
            sources_metadata = [
                {
                    "id": s.id,
                    "title": s.title,
                    "score": s.score,
                    "doc_type": s.doc_type,
                    "source": s.source,
                }
                for s in retrieval_result.results
            ]

            yield f"data: {self._json({'type': 'metadata', 'mode': response_mode.value, 'sources': sources_metadata, 'search_time_ms': retrieval_ms})}\n\n"

            # Step 4: Build context and stream LLM response
            context_text = self._build_llm_context(retrieval_result.results)
            system_prompt = self._build_system_prompt(
                response_mode.value, retrieval_result.results, context_text
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Fråga: {question}"},
            ]

            if history:
                messages.insert(1, *history)

            # Stream LLM tokens
            full_answer = ""
            final_stats = None

            async for token, stats in self.llm_service.chat_stream(
                messages=messages,
                config_override=self.query_processor.get_mode_config(response_mode.value),
            ):
                if token:
                    full_answer += token
                    yield f"data: {self._json({'type': 'token', 'content': token})}\n\n"
                else:
                    final_stats = stats

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
from functools import lru_cache


@lru_cache()
def get_orchestrator_service(
    config=None,
    llm_service=None,
    query_processor=None,
    guardrail=None,
    retrieval=None,
    reranker=None,
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
    )
