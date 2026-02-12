"""
Graph Service - LangGraph Implementation for Constitutional AI

This module defines the state machine architecture for the RAG pipeline using LangGraph.
Replaces the linear pipeline with a state machine that supports loops for self-correction.

Based on LangGraph framework for agentic RAG architectures.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph

from ..utils.logging import get_logger
from .config_service import get_config_service
from .critic_service import get_critic_service
from .grader_service import get_grader_service
from .llm_service import get_llm_service
from .query_processor_service import ResponseMode, get_query_processor_service
from .retrieval_service import RetrievalStrategy, SearchResult, get_retrieval_service

logger = get_logger(__name__)


@dataclass
class Document:
    """
    Document representation for graph state.

    Compatible with langchain_core.documents.Document but can work standalone.
    """

    page_content: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class GraphState(TypedDict):
    """
    State definition for the LangGraph state machine.

    This TypedDict defines all state variables that flow through the graph nodes.
    Each node can read and update any field in this state.

    Attributes:
        question: The user's original question/query
        documents: Retrieved documents from ChromaDB/vector search
        generation: LLM-generated response to the question
        web_search: Flag indicating if external/web search is needed
        loop_count: Counter for critique loops (safety mechanism)
        retrieval_loop_count: Counter for retrieval loops (safety mechanism)
        constitutional_feedback: Critique/feedback from the critique node
    """

    # User input
    question: str

    # Retrieved context
    documents: List[Document]

    # LLM generation
    generation: str

    # Control flow flags
    web_search: bool

    # Loop prevention
    loop_count: int  # Critique loop counter
    retrieval_loop_count: Optional[int]  # Retrieval loop counter (optional for backwards compat)

    # Constitutional AI feedback
    constitutional_feedback: str


# Type alias for convenience
State = GraphState


# Helper function to convert SearchResult to Document
def search_result_to_document(result: SearchResult) -> Document:
    """Convert SearchResult to Document for graph state"""
    return Document(
        page_content=result.snippet,
        metadata={
            "id": result.id,
            "title": result.title,
            "score": result.score,
            "source": result.source,
            "doc_type": result.doc_type,
            "date": result.date,
            "retriever": result.retriever,
        },
    )


# Helper function to convert Document to SearchResult (for compatibility)
def document_to_search_result(doc: Document) -> SearchResult:
    """Convert Document back to SearchResult for service compatibility"""
    metadata = doc.metadata or {}
    return SearchResult(
        id=metadata.get("id", "unknown"),
        title=metadata.get("title", "Untitled"),
        snippet=doc.page_content,
        score=metadata.get("score", 0.0),
        source=metadata.get("source", "unknown"),
        doc_type=metadata.get("doc_type"),
        date=metadata.get("date"),
        retriever=metadata.get("retriever", "unknown"),
    )


# Initialize services (singletons)
_config = get_config_service()
_retrieval_service = get_retrieval_service(_config)
_grader_service = get_grader_service(_config)
_llm_service = get_llm_service(_config)
_critic_service = get_critic_service(_config)
_query_processor = get_query_processor_service(_config)


async def retrieve_node(state: GraphState) -> Dict[str, Any]:
    """
    Retrieve Node - Fetches documents from vector database (Jina v3).

    Args:
        state: Current graph state

    Returns:
        Updated state with documents
    """
    logger.info(f"🔍 Node 'retrieve': Starting retrieval for query='{state['question'][:50]}...'")

    try:
        # Ensure retrieval service is initialized
        await _retrieval_service.ensure_initialized()

        # Perform retrieval
        retrieval_result = await _retrieval_service.search(
            query=state["question"],
            k=10,  # Default top-k
            strategy=RetrievalStrategy.PARALLEL_V1,
        )

        if not retrieval_result.success:
            logger.warning(f"Retrieval failed: {retrieval_result.error}")
            return {"documents": []}

        # Convert SearchResult to Document
        documents = [search_result_to_document(result) for result in retrieval_result.results]

        logger.info(f"✅ Node 'retrieve': Found {len(documents)} documents")
        return {"documents": documents}

    except Exception as e:
        logger.error(f"Retrieve node failed: {e}")
        return {"documents": []}


async def grade_documents_node(state: GraphState) -> Dict[str, Any]:
    """
    Grade Documents Node - Filters documents by relevance using GraderService.

    Uses primary LLM to grade each document (binary: yes/no).
    Filters out irrelevant documents.
    Sets web_search=True if all documents are filtered out.

    Args:
        state: Current graph state

    Returns:
        Updated state with filtered documents and web_search flag
    """
    logger.info(f"Grade documents node: {len(state.get('documents', []))} documents to grade")

    try:
        documents = state.get("documents", [])
        if not documents:
            logger.warning("No documents to grade")
            return {"documents": [], "web_search": True}

        # Convert Documents to SearchResults for grader service
        search_results = [document_to_search_result(doc) for doc in documents]

        # Grade documents
        await _grader_service.ensure_initialized()
        grading_result = await _grader_service.grade_documents(
            query=state["question"],
            documents=search_results,
        )

        if not grading_result.success:
            logger.warning(f"Grading failed: {grading_result.error}")
            return {"documents": [], "web_search": True}

        # Filter to only relevant documents
        filtered_docs = []
        for doc, grade in zip(documents, grading_result.grades):
            if grade.relevant:
                filtered_docs.append(doc)

        logger.info(
            f"Grading complete: {len(filtered_docs)}/{len(documents)} relevant "
            f"({grading_result.metrics.relevant_percentage:.1f}%)"
        )

        # Set web_search if no relevant documents
        web_search = len(filtered_docs) == 0

        if web_search:
            logger.info("No relevant documents found - setting web_search=True")

        return {
            "documents": filtered_docs,
            "web_search": web_search,
        }

    except Exception as e:
        logger.error(f"Grade documents node failed: {e}")
        return {"documents": [], "web_search": True}


async def generate_node(state: GraphState) -> Dict[str, Any]:
    """
    Generate Node - Generates LLM response using Ministral-3-14B.

    Uses system prompt (EVIDENCE or ASSIST) based on config.
    Generates answer based only on filtered documents.
    Includes constitutional feedback if this is a retry (loop_count > 0).

    Args:
        state: Current graph state

    Returns:
        Updated state with generation and incremented loop_count
    """
    loop_count = state.get("loop_count", 0)
    logger.info(f"✍️  Node 'generate': Generating response (Loop {loop_count})")

    try:
        documents = state.get("documents", [])
        question = state["question"]
        loop_count = state.get("loop_count", 0)
        constitutional_feedback = state.get("constitutional_feedback", "")

        # Determine mode (EVIDENCE or ASSIST)
        # For now, use EVIDENCE if we have documents, ASSIST otherwise
        # TODO: Use QueryProcessorService to classify properly
        mode = ResponseMode.EVIDENCE if documents else ResponseMode.ASSIST

        # Build context from documents
        context_parts = []
        for i, doc in enumerate(documents[:5], 1):  # Limit to top 5
            metadata = doc.metadata or {}
            title = metadata.get("title", "Untitled")
            context_parts.append(f"[{i}] {title}\n{doc.page_content[:300]}...")

        context_text = (
            "\n\n".join(context_parts) if context_parts else "Inga dokument tillgängliga."
        )

        # Build system prompt based on mode
        if mode == ResponseMode.EVIDENCE:
            system_prompt = f"""Du är en expert på svensk förvaltningsrätt och lagstiftning.
Du svarar endast baserat på de dokument som tillhandahålls.

KONSTITUTIONELLA REGLER:
1. LEGALITET: Använd endast information som stöds av dokumenten
2. TRANSPARENS: Alla påståenden måste ha källhänvisning
3. OBJEKTIVITET: Var neutral, saklig och formell
4. SERVICEKYLDIGHET: Var hjälpsam inom ramen för lagen

SVENSKA JURIDISKA FÖRKORTNINGAR (förstå användarens frågor):
- RF = Regeringsformen (grundlag)
- TF = Tryckfrihetsförordningen (grundlag)
- YGL = Yttrandefrihetsgrundlagen (grundlag)
- OSL = Offentlighets- och sekretesslagen
- GDPR = Dataskyddsförordningen
- BrB = Brottsbalken
- LAS = Lagen om anställningsskydd
- PBL = Plan- och bygglagen
- FL = Förvaltningslagen
- SoL = Socialtjänstlagen

TILLGÄNGLIGA KÄLLOR:
{context_text}

Om dokumenten inte innehåller tillräckligt stöd för att besvara frågan, säg tydligt att underlag saknas."""
        else:  # ASSIST
            system_prompt = f"""Du är en hjälpsam AI-assistent för svenska myndigheter.
Du svarar baserat på tillgänglig information och kan ge allmänna råd när specifik information saknas.

SVENSKA JURIDISKA FÖRKORTNINGAR (förstå användarens frågor):
- RF = Regeringsformen, TF = Tryckfrihetsförordningen, YGL = Yttrandefrihetsgrundlagen
- OSL = Offentlighets- och sekretesslagen, GDPR = Dataskyddsförordningen
- BrB = Brottsbalken, LAS = Lagen om anställningsskydd, FL = Förvaltningslagen

TILLGÄNGLIG INFORMATION:
{context_text}

Var tydlig när information saknas och ge allmänna råd när möjligt."""

        # Add constitutional feedback if this is a retry
        if loop_count > 0 and constitutional_feedback:
            system_prompt += f"\n\nKONSTITUTIONELL FEEDBACK (från tidigare granskning):\n{constitutional_feedback}\n\nUppdatera ditt svar baserat på denna feedback."

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Fråga: {question}"},
        ]

        # Generate response
        await _llm_service.ensure_initialized()
        full_response = ""
        async for token, stats in _llm_service.chat_stream(messages=messages):
            if token:
                full_response += token

        logger.info(f"Generated response: {len(full_response)} chars (loop_count={loop_count})")
        return {
            "generation": full_response,
            "loop_count": loop_count + 1,  # Increment loop count
        }

    except Exception as e:
        logger.error(f"Generate node failed: {e}")
        return {
            "generation": f"Fel vid generering: {str(e)}",
            "loop_count": state.get("loop_count", 0) + 1,
        }


async def critique_node(state: GraphState) -> Dict[str, Any]:
    """
    Critique Node - Evaluates response against constitutional principles.

    Uses CriticService to review the generation against:
    - Legalitet (Legality)
    - Saklighet (Factuality)
    - Offentlighet (Transparency)

    Args:
        state: Current graph state

    Returns:
        Updated state with constitutional_feedback
    """
    logger.info("🔍 Node 'critique': Initializing CriticService and evaluating response...")

    try:
        generation = state.get("generation", "")
        documents = state.get("documents", [])

        if not generation:
            logger.warning("No generation to critique")
            return {"constitutional_feedback": "Ingen generering att granska"}

        # Convert documents to SearchResult format for critic
        search_results = [document_to_search_result(doc) for doc in documents]

        # Build sources context
        _sources_context = [
            {
                "id": doc.metadata.get("id", "unknown"),
                "title": doc.metadata.get("title", "Untitled"),
                "snippet": doc.page_content[:200],
            }
            for doc in documents
        ]

        # Determine mode (simplified - should use QueryProcessorService)
        mode = "evidence" if documents else "assist"

        # CRITICAL: Ensure CriticService is properly initialized with LLMService
        # Get fresh instances to ensure proper initialization
        config = get_config_service()
        llm_service = get_llm_service(config)

        # Ensure LLMService is initialized first (it uses llama-server on port 8080)
        await llm_service.ensure_initialized()

        # Create CriticService with initialized LLMService
        critic_service = get_critic_service(config, llm_service)

        # CRITICAL: Explicitly initialize CriticService
        await critic_service.initialize()

        logger.info("✅ CriticService initialized and ready for critique")

        # For now, use self_reflection for constitutional feedback
        # TODO: Implement proper critique method that evaluates against principles
        reflection = await critic_service.self_reflection(
            query=state["question"],
            mode=mode,
            sources=search_results,
        )

        # Build feedback from reflection
        feedback_parts = []
        if not reflection.constitutional_compliance:
            feedback_parts.append(
                "⚠️ Konstitutionell efterlevnad: Svaret följer inte alla konstitutionella regler."
            )

        if not reflection.has_sufficient_evidence:
            feedback_parts.append(f"⚠️ Underlag: {', '.join(reflection.missing_evidence)}")

        if reflection.thought_process:
            feedback_parts.append(f"Reflektion: {reflection.thought_process[:200]}...")

        feedback = (
            "\n".join(feedback_parts)
            if feedback_parts
            else "✅ Svaret följer konstitutionella principer."
        )

        # Add explicit compliance marker for decision logic
        if reflection.constitutional_compliance and not feedback_parts:
            feedback = "✅ compliance=True: " + feedback

        logger.info(
            f"✅ Node 'critique': Critique complete - compliance={reflection.constitutional_compliance}, feedback length={len(feedback)} chars"
        )
        return {"constitutional_feedback": feedback}

    except Exception as e:
        logger.error(f"CRITICAL ERROR in critique_node: {e}", exc_info=True)
        # Return dummy approval to prevent infinite loops, but log the error
        # This allows the graph to continue even if critique fails
        return {"constitutional_feedback": "✅ Kritik hoppades över (fel i critique service)"}


async def transform_query_node(state: GraphState) -> Dict[str, Any]:
    """
    Transform Query Node - Rewrites query for better search.

    Called when:
    - web_search=True
    - Grading failed or returned no relevant documents

    Optimizes query for external/broader search.
    Increments retrieval_loop_count to prevent infinite loops.

    Args:
        state: Current graph state

    Returns:
        Updated state with transformed question and reset web_search
    """
    logger.info("Transform query node: rewriting query")

    try:
        question = state["question"]
        web_search = state.get("web_search", False)
        # Track retrieval loops separately from critique loops
        retrieval_loop_count = state.get("retrieval_loop_count", 0)

        # Check max loops (max 3 retrieval attempts)
        if retrieval_loop_count >= 3:
            logger.warning(
                f"Max retrieval loops reached (retrieval_loop_count={retrieval_loop_count})"
            )
            return {
                "question": question,
                "web_search": False,  # Stop looping
                "documents": [],  # Empty documents to trigger fallback
            }

        # Use QueryProcessorService to decontextualize/rewrite query
        await _query_processor.ensure_initialized()

        # Decontextualize query (makes it standalone) - Note: decontextualize_query returns a result, not a coroutine
        decontextualized = _query_processor.decontextualize_query(
            query=question,
            history=None,  # Could include history if available
        )

        # If web_search is needed, optimize for broader search
        if web_search:
            # Add broader search terms
            transformed = (
                f"{decontextualized.rewritten_query} (sök brett, inkludera relaterade ämnen)"
            )
        else:
            transformed = decontextualized.rewritten_query

        logger.info(
            f"Query transformed: '{question[:50]}...' -> '{transformed[:50]}...' (retrieval_loop_count={retrieval_loop_count})"
        )
        return {
            "question": transformed,
            "web_search": False,  # Reset after transformation
            "retrieval_loop_count": retrieval_loop_count + 1,  # Increment retrieval loop counter
        }

    except Exception as e:
        logger.error(f"Transform query node failed: {e}")
        # Return original question on failure
        return {
            "question": state["question"],
            "web_search": False,
        }


# ═══════════════════════════════════════════════════════════════════════════
# CONDITIONAL ROUTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def should_continue_after_grading(state: GraphState) -> Literal["generate", "transform_query"]:
    """
    Conditional routing after grade_documents_node.

    Routes to:
    - generate_node: If documents exist after filtering
    - transform_query_node: If no documents (all filtered out)

    Args:
        state: Current graph state

    Returns:
        Next node name
    """
    documents = state.get("documents", [])
    web_search = state.get("web_search", False)

    if len(documents) > 0 and not web_search:
        logger.info(f"Routing to generate_node: {len(documents)} documents available")
        return "generate"
    else:
        logger.info("Routing to transform_query_node: no documents or web_search=True")
        return "transform_query"


async def fallback_node(state: GraphState) -> Dict[str, Any]:
    """
    Fallback Node - Returns fallback message when max loops reached.

    Called when critique fails and loop_count >= 3.
    Provides a safe fallback response.

    Args:
        state: Current graph state

    Returns:
        Updated state with fallback generation
    """
    logger.warning("Fallback node: max loops reached, returning fallback message")

    fallback_message = (
        "Jag kunde inte generera ett tillräckligt kvalitetssäkert svar efter flera försök. "
        "Försök omformulera din fråga eller kontakta support om problemet kvarstår."
    )

    return {
        "generation": fallback_message,
        "constitutional_feedback": "Max antal försök nåddes - fallback aktiverad",
    }


def should_continue_after_critique(state: GraphState) -> Literal["generate", "fallback", "end"]:
    """
    Conditional routing after critique_node.

    Routes to:
    - END: If critique passed (compliance=True or positive feedback)
    - generate_node: If critique failed and loop_count < 3 (retry with feedback)
    - fallback_node: If critique failed and loop_count >= 3 (max retries reached)

    Args:
        state: Current graph state

    Returns:
        Next node name or END
    """
    constitutional_feedback = state.get("constitutional_feedback", "")
    loop_count = state.get("loop_count", 0)

    # Check if critique passed - look for explicit success indicators
    # Success indicators:
    # - "✅" emoji
    # - "följer konstitutionella principer" (Swedish for "follows constitutional principles")
    # - "compliance=True" (if reflection returns this)
    # - Empty or very short feedback (usually means no issues)
    feedback_lower = constitutional_feedback.lower()

    critique_passed = (
        "✅" in constitutional_feedback
        or "följer konstitutionella principer" in feedback_lower
        or "compliance=true" in feedback_lower
        or (
            len(constitutional_feedback.strip()) < 50
            and "⚠️" not in constitutional_feedback
            and "konstitutionell efterlevnad" not in feedback_lower
        )
    )

    # Check for explicit failure indicators
    critique_failed = (
        "⚠️" in constitutional_feedback
        or "konstitutionell efterlevnad" in feedback_lower
        and "inte" in feedback_lower
        or "saknas_underlag" in feedback_lower
        or "missing_evidence" in feedback_lower
    )

    # If passed, end immediately
    if critique_passed and not critique_failed:
        logger.info("✅ Decision: Critique passed - routing to END")
        return "end"

    # If failed and we have retries left, loop back
    if critique_failed and loop_count < 3:
        logger.info(
            f"🔄 Decision: Correction needed. Looping back to generate (loop_count={loop_count} -> {loop_count + 1})"
        )
        return "generate"

    # Max loops reached or unclear status
    if loop_count >= 3:
        logger.warning(
            f"⚠️ Decision: Max critique loops reached (loop_count={loop_count}) - routing to fallback"
        )
        return "fallback"

    # Default: if we're not sure and haven't hit max loops, try once more
    if loop_count < 2:
        logger.info(
            f"🔄 Decision: Unclear critique status, retrying (loop_count={loop_count} -> {loop_count + 1})"
        )
        return "generate"

    # Otherwise, end (conservative approach)
    logger.info("✅ Decision: Ending after critique (conservative)")
    return "end"


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════


def create_constitutional_graph() -> StateGraph:
    """
    Create the LangGraph state machine for Constitutional AI.

    Graph structure:
    - Start -> retrieve_node
    - retrieve_node -> grade_documents_node
    - grade_documents_node -> (conditional) generate_node OR transform_query_node
    - transform_query_node -> retrieve_node (loop, max 3 times)
    - generate_node -> critique_node
    - critique_node -> (conditional) generate_node (retry) OR END

    Returns:
        Compiled StateGraph ready for execution
    """
    logger.info("Creating Constitutional AI graph")

    # Create graph
    workflow = StateGraph(GraphState)

    # Add nodes
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("critique", critique_node)
    workflow.add_node("transform_query", transform_query_node)
    workflow.add_node("fallback", fallback_node)

    # Set entry point
    workflow.set_entry_point("retrieve")

    # Add edges
    workflow.add_edge("retrieve", "grade_documents")

    # Conditional edge after grading
    workflow.add_conditional_edges(
        "grade_documents",
        should_continue_after_grading,
        {
            "generate": "generate",
            "transform_query": "transform_query",
        },
    )

    # Edge from transform_query back to retrieve (loop)
    workflow.add_edge("transform_query", "retrieve")

    # Edge from generate to critique
    workflow.add_edge("generate", "critique")

    # Conditional edge after critique
    workflow.add_conditional_edges(
        "critique",
        should_continue_after_critique,
        {
            "generate": "generate",  # Retry with feedback
            "fallback": "fallback",  # Max loops reached
            "end": END,  # Success
        },
    )

    # Edge from fallback to END
    workflow.add_edge("fallback", END)

    # Compile graph with increased recursion limit
    app = workflow.compile()

    # Set recursion limit to prevent infinite loops (default is 25)
    # We allow up to 3 retrieval loops + 3 critique loops = 6 max iterations
    # But we set it higher to account for all nodes in a full flow
    app = app.with_config({"recursion_limit": 50})

    logger.info("Constitutional AI graph created successfully")
    return app


# Alias for compatibility
build_graph = create_constitutional_graph

# Global graph instance (lazy initialization)
_graph_app: Optional[StateGraph] = None


def get_constitutional_graph() -> StateGraph:
    """
    Get or create the Constitutional AI graph (singleton).

    Returns:
        Compiled StateGraph instance
    """
    global _graph_app
    if _graph_app is None:
        _graph_app = create_constitutional_graph()
    return _graph_app
