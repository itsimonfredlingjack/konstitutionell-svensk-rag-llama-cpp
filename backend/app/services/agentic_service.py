"""
Agentic Service — LangGraph-based agentic RAG flow.

Extracted from orchestrator_service.py (Sprint 2, Task #19).
Handles the state machine approach to RAG with self-correction loops.
"""

import time
from typing import Any, List, Optional

from ..utils.logging import get_logger
from .config_service import ConfigService
from .graph_service import build_graph, GraphState
from .guardrail_service import WardenStatus
from .query_processor_service import QueryProcessorService, ResponseMode
from .rag_models import RAGPipelineMetrics, RAGResult
from .retrieval_service import SearchResult

logger = get_logger(__name__)


async def run_agentic_flow(
    *,
    config: ConfigService,
    query_processor: QueryProcessorService,
    llm_service: Any,
    guardrail: Any,
    agent_app: Optional[Any],
    question: str,
    mode: Optional[str] = "auto",
    resolve_mode_fn,
) -> tuple[RAGResult, Any]:
    """
    Run query through LangGraph agentic flow.

    Returns (RAGResult, agent_app) — agent_app may be newly initialized.
    """
    start_time = time.perf_counter()
    reasoning_steps: List[str] = []

    logger.info(f"Running Agentic Flow for query: '{question[:50]}...'")

    try:
        if agent_app is None:
            agent_app = build_graph()
            logger.info("LangGraph agentic flow initialized")

        classification = query_processor.classify_query(question)
        resolved_mode = resolve_mode_fn(mode, classification.mode)

        if resolved_mode == ResponseMode.CHAT:
            messages = [
                {"role": "system", "content": "Avslappnad AI-assistent. Svara kort på svenska."},
                {"role": "user", "content": question},
            ]
            full_answer = ""
            async for token, stats in llm_service.chat_stream(
                messages=messages, config_override={"temperature": 0.1, "num_predict": 512}
            ):
                if token:
                    full_answer += token

            return RAGResult(
                answer=full_answer,
                sources=[],
                reasoning_steps=["CHAT mode: Direct response"],
                metrics=RAGPipelineMetrics(
                    total_pipeline_ms=(time.perf_counter() - start_time) * 1000, mode="chat"
                ),
                mode=resolved_mode,
                guardrail_status=WardenStatus.UNCHANGED,
                evidence_level="NONE",
            ), agent_app

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
        final_state = await agent_app.ainvoke(initial_state)

        final_answer = final_state.get("generation", "")
        loop_count = final_state.get("loop_count", 0)
        retrieval_loop_count = final_state.get("retrieval_loop_count", 0)

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

        guardrail_result = guardrail.validate_response(
            text=final_answer, query=question, mode=resolved_mode.value
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
        ), agent_app

    except Exception as e:
        logger.error(f"Agentic flow failed: {e}")
        return RAGResult(
            answer="Ett fel uppstod vid bearbetning av din fråga. Försök igen.",
            sources=[],
            reasoning_steps=reasoning_steps + [f"Error: {str(e)}"],
            metrics=RAGPipelineMetrics(
                total_pipeline_ms=(time.perf_counter() - start_time) * 1000, mode="error"
            ),
            mode=ResponseMode.ASSIST,
            guardrail_status=WardenStatus.UNCHANGED,
            evidence_level="NONE",
            success=False,
            error=str(e),
        ), agent_app
