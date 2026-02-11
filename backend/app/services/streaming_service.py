"""
Streaming Service — SSE streaming RAG pipeline.

Extracted from orchestrator_service.py (Sprint 2, Task #19).
Handles the streaming version of the RAG pipeline with Server-Sent Events.
"""

import asyncio
import json
import time
from typing import Any, AsyncGenerator, List, Optional

from ..utils.logging import get_logger
from .config_service import ConfigService
from .query_processor_service import QueryProcessorService, ResponseMode
from .retrieval_service import RetrievalStrategy, SearchResult

logger = get_logger(__name__)


def _json(data: dict) -> str:
    return json.dumps(data)


async def stream_query(
    *,
    config: ConfigService,
    query_processor: QueryProcessorService,
    llm_service: Any,
    guardrail: Any,
    retrieval: Any,
    reranker: Any,
    grader: Any,
    critic: Any,
    resolve_mode_fn,
    build_llm_context_fn,
    retrieve_examples_fn,
    format_examples_fn,
    build_system_prompt_fn,
    question: str,
    mode: Optional[str] = "auto",
    k: int = 10,
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.ADAPTIVE,
    history: Optional[List[dict]] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream RAG pipeline with Server-Sent Events.

    Yields SSE-formatted events: metadata, token, corrections, done, error.
    """
    start_time = time.perf_counter()

    try:
        # SECURITY: Check query safety
        is_safe, safety_reason = guardrail.check_query_safety(question)
        if not is_safe:
            logger.warning(f"Query blocked by safety check: {safety_reason}")
            yield f"data: {_json({'type': 'error', 'error': 'Fragan blockerades av sakerhetsskal'})}\n\n"
            return

        # Step 1: Classify query
        classification = query_processor.classify_query(question)
        response_mode = resolve_mode_fn(mode, classification.mode)

        # Prefetch examples while retrieval runs (only depends on question + mode)
        examples_task = asyncio.ensure_future(
            retrieve_examples_fn(query=question, mode=response_mode.value, k=2)
        )

        if response_mode == ResponseMode.CHAT:
            examples_task.cancel()
            yield f"data: {_json({'type': 'metadata', 'mode': 'chat'})}\n\n"
            async for token, _ in llm_service.chat_stream(
                messages=[
                    {
                        "role": "system",
                        "content": "Avslappnad AI-assistent. Svara kort på svenska.",
                    },
                    {"role": "user", "content": question},
                ],
                config_override={"temperature": 0.1, "num_predict": 512},
            ):
                yield f"data: {_json({'type': 'token', 'content': token})}\n\n"
            yield f"data: {_json({'type': 'done'})}\n\n"
            return

        # Step 2: Decontextualization
        if history:
            decont_result = query_processor.decontextualize_query(question, history)
            search_query = decont_result.rewritten_query
            yield f"data: {_json({'type': 'decontextualized', 'original': question, 'rewritten': search_query})}\n\n"
        else:
            search_query = question

        # Step 3: Retrieval (EPR)
        retrieval_start = time.perf_counter()
        history_for_retrieval = None
        if history:
            history_for_retrieval = [
                f"{h.get('role', 'user')}: {h.get('content', '')}"
                for h in history
                if h.get("content")
            ]

        retrieval_result = await retrieval.search_with_epr(
            query=search_query,
            k=k,
            where_filter=None,
            history=history_for_retrieval,
        )
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
        yield f"data: {_json({'type': 'phase', 'phase': 'retrieval_complete', 'latency_ms': retrieval_ms})}\n\n"

        # CRAG: Document Grading & Filtering
        sources = retrieval_result.results
        thought_chain = None

        # Emit phase start for CRAG grading
        if config.settings.crag_enabled and grader:
            yield f"data: {_json({'type': 'phase', 'phase': 'grading_start'})}\n\n"
        if config.settings.crag_enabled and grader:
            grading_result = await grader.grade_documents(
                query=search_query, documents=retrieval_result.results
            )
            yield f"data: {_json({'type': 'grading', 'total': grading_result.metrics.total_documents, 'relevant': grading_result.metrics.relevant_count})}\n\n"

            relevant_docs = [
                doc
                for doc, grade in zip(retrieval_result.results, grading_result.grades)
                if grade.relevant
            ]
            sources = relevant_docs if relevant_docs else []

        # CRAG: Self-Reflection
        if (
            sources
            and config.settings.crag_enabled
            and config.settings.crag_enable_self_reflection
            and critic
        ):
            reflection = await critic.self_reflection(
                query=question, mode=response_mode.value, sources=sources
            )
            thought_chain = reflection.thought_process
            yield f"data: {_json({'type': 'thought_chain', 'content': thought_chain})}\n\n"

            if not reflection.has_sufficient_evidence and response_mode == ResponseMode.EVIDENCE:
                examples_task.cancel()
                refusal_text = getattr(
                    config.settings,
                    "evidence_refusal_template",
                    "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
                )
                refusal_reason = (
                    ", ".join(reflection.missing_evidence)
                    if reflection.missing_evidence
                    else "Underlag saknas"
                )
                yield f"data: {_json({'type': 'metadata', 'mode': response_mode.value, 'sources': [], 'search_time_ms': retrieval_ms, 'refusal': True, 'refusal_reason': refusal_reason, 'evidence_level': 'NONE'})}\n\n"
                yield f"data: {_json({'type': 'refusal', 'message': refusal_text, 'reason': refusal_reason})}\n\n"
                yield f"data: {_json({'type': 'token', 'content': refusal_text})}\n\n"
                yield f"data: {_json({'type': 'done'})}\n\n"
                return

        # EVIDENCE mode with no sources: force refusal
        if response_mode == ResponseMode.EVIDENCE and not sources:
            examples_task.cancel()
            refusal_text = getattr(
                config.settings,
                "evidence_refusal_template",
                "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats...",
            )
            yield f"data: {_json({'type': 'metadata', 'mode': response_mode.value, 'sources': [], 'search_time_ms': retrieval_ms, 'refusal': True, 'evidence_level': 'NONE'})}\n\n"
            yield f"data: {_json({'type': 'token', 'content': refusal_text})}\n\n"
            yield f"data: {_json({'type': 'done'})}\n\n"
            return

        # Reranking
        if (
            config.settings.reranking_enabled
            and reranker
            and response_mode != ResponseMode.CHAT
            and sources
        ):
            rerank_result = await reranker.rerank(
                query=search_query,
                documents=[
                    {"id": s.id, "title": s.title, "snippet": s.snippet, "score": s.score}
                    for s in sources
                ],
                top_k=len(sources),
            )
            threshold = config.settings.reranking_score_threshold
            top_n = config.settings.reranking_top_n
            filtered = []
            for i, doc in enumerate(rerank_result.reranked_docs):
                score = rerank_result.reranked_scores[i]
                if score >= threshold and len(filtered) < top_n:
                    orig = next((s for s in sources if s.id == doc["id"]), None)
                    if orig:
                        filtered.append(
                            SearchResult(
                                id=orig.id,
                                title=orig.title,
                                snippet=orig.snippet,
                                score=score,
                                source=orig.source,
                                doc_type=orig.doc_type,
                                date=orig.date,
                                retriever=orig.retriever,
                                tier=orig.tier,
                            )
                        )
            sources = filtered

        # Compute evidence level from final (reranked) sources
        evidence_level = query_processor.determine_evidence_level(
            sources=[{"score": s.score, "doc_type": s.doc_type} for s in sources],
            answer="",
        )

        # Emit metadata with sources
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
        yield f"data: {_json({'type': 'metadata', 'mode': response_mode.value, 'sources': sources_metadata, 'search_time_ms': retrieval_ms, 'evidence_level': evidence_level.value.upper()})}\n\n"

        yield f"data: {_json({'type': 'phase', 'phase': 'generation_start'})}\n\n"

        # Step 4: Build context and stream LLM response
        context_text = build_llm_context_fn(sources)
        try:
            examples = await examples_task
        except (asyncio.CancelledError, Exception):
            examples = []
        examples_text = format_examples_fn(examples)

        system_prompt = build_system_prompt_fn(
            response_mode.value,
            sources,
            context_text,
            structured_output_enabled=False,
            user_query=question,
        )
        system_prompt = system_prompt.replace("{{CONSTITUTIONAL_EXAMPLES}}", examples_text)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Fråga: {question}"},
        ]
        if history:
            for i, msg in enumerate(history):
                messages.insert(1 + i, msg)

        full_answer = ""
        async for token, stats in llm_service.chat_stream(
            messages=messages,
            config_override=query_processor.get_mode_config(response_mode.value),
        ):
            if token:
                full_answer += token
                yield f"data: {_json({'type': 'token', 'content': token})}\n\n"

        # Step 5: Guardrail corrections
        guardrail_result = guardrail.validate_response(
            text=full_answer, query=question, mode=response_mode.value
        )
        if guardrail_result.corrections:
            yield f"data: {_json({'type': 'corrections', 'corrections': [c.original_term + ' → ' + c.corrected_term for c in guardrail_result.corrections], 'corrected_text': guardrail_result.corrected_text})}\n\n"

        total_ms = (time.perf_counter() - start_time) * 1000
        yield f"data: {_json({'type': 'done', 'total_time_ms': total_ms})}\n\n"

    except Exception as e:
        yield f"data: {_json({'type': 'error', 'message': str(e)})}\n\n"
