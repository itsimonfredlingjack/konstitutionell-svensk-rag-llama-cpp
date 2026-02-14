# Orchestrator Decomposition Analysis

**Date:** 2026-02-07
**Author:** Lead (Opus 4.6)
**File:** `backend/app/services/orchestrator_service.py` (2517 lines)

## Current State

The orchestrator is a **god class** that owns the entire RAG pipeline. It contains:
- 6 dataclasses/inner classes (ResponseTemplates, RAGPipelineMetrics, Citation, RAGResult, CragResult, OrchestratorService)
- 2 standalone functions (get_answer_contract, get_orchestrator_service)
- A dict constant (ANSWER_CONTRACTS — ~80 lines of Swedish prompt templates)
- 15+ methods spanning query processing, CRAG grading, prompt building, streaming, etc.

### Critical Problem: Dual Pipeline Duplication

`process_query()` (lines 618-1430, ~812 lines) and `stream_query()` (lines 1913-2200, ~287 lines) implement the **same pipeline** with different output formats:
1. Classify query
2. Decontextualize (if history)
3. Retrieve documents (EPR routing)
4. CRAG grading + self-reflection
5. Rerank
6. Build context
7. Build system prompt
8. LLM generation
9. Guardrail validation

Any change to the pipeline must be made in BOTH methods. This is the #1 source of bugs and tech debt.

## Decomposition Plan: 5 Extractable Modules

### Module 1: `pipeline_service.py` (NEW — most critical)

**Purpose:** Unified RAG pipeline that both `process_query` and `stream_query` call.

Extract the shared pipeline logic into a single `RAGPipeline` class:
```python
class RAGPipeline:
    async def execute(self, request: PipelineRequest) -> PipelineResult:
        """Execute full pipeline, returning structured result."""
    
    async def execute_streaming(self, request: PipelineRequest) -> AsyncGenerator[PipelineEvent, None]:
        """Execute pipeline, yielding events for SSE streaming."""
```

**Extracts from orchestrator:**
- Steps 1-5 of process_query (classify → decontextualize → retrieve → CRAG → rerank)
- The parallel logic in stream_query
- `_resolve_query_mode()`, `_build_llm_context()`

**Lines saved:** ~600 (most of the duplication)

### Module 2: `prompt_service.py` (NEW)

**Purpose:** All prompt construction and answer contracts.

Extract:
- `ResponseTemplates` class (lines 48-65)
- `ANSWER_CONTRACTS` dict (lines 68-123)
- `get_answer_contract()` function
- `_build_system_prompt()` method (lines 1619-1912, **293 lines\!** — the largest single method)
- `_format_constitutional_examples()` method
- `_retrieve_constitutional_examples()` method (lines 1515-1583)

**Lines saved:** ~500

### Module 3: `crag_service.py` (NEW)

**Purpose:** Corrective RAG pipeline (grading + self-reflection + refusal logic).

Extract:
- `_process_crag_grading()` method (lines 2261-2453, **192 lines**)
- The inline `CragResult` dataclass
- CRAG logic from both `process_query` and `stream_query`
- Integration with `grader_service.py` and `critic_service.py`

**Dependencies:** GraderService, CriticService, ConfigService
**Lines saved:** ~250

### Module 4: `models.py` (NEW — data models extraction)

**Purpose:** All dataclasses and type definitions currently in orchestrator.

Extract:
- `RAGPipelineMetrics` (lines 130-215)
- `Citation` (lines 216-226)
- `RAGResult` (lines 227-278)
- `ResponseTemplates` (if not moving to prompt_service)

**Lines saved:** ~150

### Module 5: Keep existing services but thin the orchestrator

**Already extracted services that are fine:**
- `llm_service.py` (705 lines) — LLM communication ✅
- `retrieval_service.py` (883 lines) — document retrieval ✅
- `reranking_service.py` (356 lines) — Jina reranker v2 ✅
- `guardrail_service.py` (607 lines) — safety validation ✅
- `grader_service.py` (529 lines) — CRAG grading ✅
- `critic_service.py` (522 lines) — self-reflection ✅
- `query_processor_service.py` (529 lines) — classification ✅

**Needs cleanup:**
- `retrieval_orchestrator.py` (1357 lines) — overlaps with retrieval_service.py, needs audit
- `graph_service.py` (740 lines) — LangGraph state machine, used by `run_agentic_flow()` only

## Extraction Order

1. **models.py** first (zero risk, just move dataclasses)
2. **prompt_service.py** second (self-contained, huge system prompts)
3. **crag_service.py** third (well-defined boundary)
4. **pipeline_service.py** last (most complex, eliminates duplication)

After extraction, orchestrator becomes a thin coordinator (~300-400 lines):
```python
class OrchestratorService(BaseService):
    def __init__(self, pipeline, prompt_service, crag_service, ...):
        ...
    
    async def process_query(self, **kwargs) -> RAGResult:
        return await self.pipeline.execute(PipelineRequest(**kwargs))
    
    async def stream_query(self, **kwargs) -> AsyncGenerator:
        async for event in self.pipeline.execute_streaming(PipelineRequest(**kwargs)):
            yield event.to_sse()
    
    async def health_check(self) -> bool: ...
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Breaking existing API | HIGH | Tests FIRST, then extract |
| Circular imports | MEDIUM | models.py has zero deps, extract first |
| `retrieval_orchestrator.py` overlap | MEDIUM | Audit before extracting pipeline |
| `graph_service.py` integration | LOW | It already has clean boundary |
| Singleton pattern with `@lru_cache` | MEDIUM | Move to proper DI container |

## Dependencies to Audit

The orchestrator imports from 12 other modules:
- core.exceptions (SecurityViolationError)
- utils.logging, utils.metrics
- base_service, config_service
- critic_service, embedding_service, grader_service
- graph_service, guardrail_service, llm_service
- query_processor_service, reranking_service
- retrieval_service, structured_output_service
- intent_classifier

No circular imports exist currently — extraction should be safe.
