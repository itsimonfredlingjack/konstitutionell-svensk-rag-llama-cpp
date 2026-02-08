# Orchestrator Service Decomposition Analysis

**File**: `backend/app/services/orchestrator_service.py`  
**Current Lines**: 2517 (largest service in project)  
**Analysis Date**: 2025-02-07  
**Status**: Ready for refactoring

---

## Executive Summary

The `OrchestratorService` is a monolithic orchestrator with 11 public/async methods spanning 2517 lines. It violates Single Responsibility Principle by handling:

1. **Pipeline Orchestration** (main coordinator) ✓ Legitimate
2. **CRAG Grading Logic** (Corrective RAG evaluation) → Extractable
3. **Prompt Engineering** (system prompt building) → Extractable
4. **Constitutional Examples** (in-context learning) → Extractable
5. **Response Sanitization** (answer validation) → Extractable
6. **Chat Mode Processing** (special case handler) → Extractable
7. **Stream Processing** (server-sent events) → Keep (coordination)

**Decomposition Target**: Reduce to ~600-700 lines (pure orchestration) by extracting 5-6 modules.

---

## 1. Current Service Breakdown

### All 25 Services by Line Count

| Service | Lines | Status |
|---------|-------|--------|
| orchestrator_service.py | 2517 | LARGE (target for decomposition) |
| retrieval_orchestrator.py | 1357 | LARGE (separate concern: retrieval) |
| retrieval_service.py | 883 | OK |
| graph_service.py | 740 | OK |
| llm_service.py | 705 | OK |
| rag_fusion.py | 629 | OK |
| guardrail_service.py | 607 | OK |
| confidence_signals.py | 595 | OK |
| query_rewriter.py | 539 | OK |
| grader_service.py | 529 | OK |
| critic_service.py | 522 | OK |
| query_processor_service.py | 529 | OK |
| intent_classifier.py | 403 | OK |
| config_service.py | 424 | OK |
| swedish_compound_splitter.py | 477 | OK |
| bm25_service.py | 271 | OK |
| structured_output_service.py | 258 | OK |
| reranking_service.py | 356 | OK |
| embedding_service.py | 209 | OK |
| intent_routing.py | 170 | OK |
| base_service.py | 127 | OK |
| legal_abbreviations.py | 273 | OK |
| sse_stream_service.py | 37 | OK |
| source_hierarchy.py | 39 | OK |
| __init__.py | 0 | OK |
| **TOTAL** | **13,196** | Good distribution after decomposition |

---

## 2. Methods to Extract

### Method 1: _process_crag_grading (192 lines)

**Lines**: 2261-2453  
**Purpose**: Grade documents, self-reflection, early return on low evidence  
**Extractable**: YES → CRAGEvaluator service

### Method 2: _build_system_prompt (293 lines)

**Lines**: 1619-1912  
**Purpose**: Build mode-specific system prompt with grounding rules  
**Extractable**: YES → PromptEngineer service

### Method 3: _retrieve_constitutional_examples (69 lines)

**Lines**: 1515-1583  
**Purpose**: Fetch RetICL examples from ChromaDB  
**Extractable**: YES → PromptEngineer service (related to prompts)

### Method 4: _format_constitutional_examples (35 lines)

**Lines**: 1584-1618  
**Purpose**: Format examples for prompt inclusion  
**Extractable**: YES → PromptEngineer service

### Method 5: _build_llm_context (24 lines)

**Lines**: 1491-1514  
**Purpose**: Build context string from search results  
**Extractable**: YES → PromptEngineer service

### Method 6: _process_chat_mode (61 lines)

**Lines**: 1430-1490  
**Purpose**: Handle CHAT mode (no RAG)  
**Extractable**: YES → ChatModeHandler service

### Method 7: _is_truncated_answer (20 lines)

**Lines**: 296-317  
**Purpose**: Detect truncated LLM outputs  
**Extractable**: YES → ResponseSanitizer utility

### Method 8: _sanitize_answer (25 lines, inline)

**Location**: Inside process_query  
**Purpose**: Clean answers, remove JSON leaks  
**Extractable**: YES → ResponseSanitizer utility

### Method 9: _json (6 lines)

**Lines**: 2454-2458  
**Purpose**: JSON encoding helper  
**Extractable**: YES → ResponseSanitizer utility

---

## 3. Extraction Plan

### Phase 1: Create ResponseSanitizer Utility (50 lines)

```python
# backend/app/utils/response_sanitizer.py
class ResponseSanitizer:
    @staticmethod
    def is_truncated(answer: str) -> bool:
        # from _is_truncated_answer (20 lines)
    
    @staticmethod
    def sanitize(answer, mode, refusal, fallback) -> tuple:
        # from _sanitize_answer (25 lines)
    
    @staticmethod
    def to_json(data: dict) -> str:
        # from _json (6 lines)
```

**Risk**: Low (pure utility)  
**Dependencies**: None  
**Tests**: Unit tests only  

---

### Phase 2: Create PromptEngineer Service (421 lines)

```python
# backend/app/services/prompt_engineer.py
class PromptEngineer(BaseService):
    async def build_prompt(mode, sources, ...) -> str:
        # Coordinates 4 methods below
    
    async def _retrieve_constitutional_examples(query, mode, k) -> List:
        # from orchestrator (69 lines)
    
    def _format_constitutional_examples(examples) -> str:
        # from orchestrator (35 lines)
    
    def _build_llm_context(sources) -> str:
        # from orchestrator (24 lines)
    
    def _build_system_prompt(...) -> str:
        # from orchestrator (293 lines)
```

**Risk**: Medium (complex logic, many modes)  
**Dependencies**: ChromaDB, EmbeddingService, ConfigService  
**Tests**: Unit + integration (RetICL retrieval)

---

### Phase 3: Create CRAGEvaluator Service (250 lines)

```python
# backend/app/services/crag_evaluator.py
@dataclass
class EvaluationResult:
    sources: List[SearchResult]
    grade_ms: float
    thought_chain: Optional[str]
    early_return: bool
    result: Optional[RAGResult]

class CRAGEvaluator(BaseService):
    async def evaluate_retrieval(
        question, search_query, retrieval_result, mode, ...
    ) -> EvaluationResult:
        # from _process_crag_grading (192 lines)
```

**Risk**: Medium (complex grading + self-reflection)  
**Dependencies**: GraderService, CriticService, ConfigService  
**Tests**: Unit tests (CRAG path), integration tests

---

### Phase 4: Create ChatModeHandler Service (80 lines)

```python
# backend/app/services/chat_handler.py
class ChatModeHandler(BaseService):
    async def process_chat(question, start_time, ...) -> RAGResult:
        # from _process_chat_mode (61 lines)
```

**Risk**: Low (isolated code path)  
**Dependencies**: LLMService, PromptEngineer  
**Tests**: Unit tests (CHAT mode)

---

## 4. Impact Summary

### Before Extraction
- **orchestrator_service.py**: 2517 lines
- **25 services total**: 13,196 lines

### After Extraction
- **orchestrator_service.py**: ~1870 lines (-647)
- **prompt_engineer.py**: +421 lines
- **crag_evaluator.py**: +250 lines
- **chat_handler.py**: +80 lines
- **response_sanitizer.py**: +50 lines
- **30 services total**: ~2671 lines (+154 class boilerplate)

### Net Benefits
✅ Orchestrator: -27% lines (2517 → 1870)  
✅ Better SRP (Single Responsibility)  
✅ Easier testing (isolated services)  
✅ Reusable components (PromptEngineer for other uses)  
✅ Backwards compatible (no API changes)

---

## 5. No Duplication with retrieval_orchestrator.py

**Question**: Should we merge OrchestratorService and RetrievalOrchestrator?

**Answer**: No, they are cleanly separated:

| Aspect | OrchestratorService | RetrievalOrchestrator |
|--------|-------------------|----------------------|
| **Role** | Full RAG pipeline | Multi-strategy search |
| **Scope** | Classify→Retrieve→Grade→Generate | Only retrieval |
| **Lines** | 2517 | 1357 |
| **Methods** | 11 | 6 |
| **Used By** | API routes | OrchestratorService |
| **Duplication** | None | ✅ Clean dependency |

**Conclusion**: Keep separate. Retrieval orchestrator is a focused dependency.

---

## 6. Testing Strategy

### ResponseSanitizer (Unit only)
```
test_is_truncated_detects_incomplete_list()
test_sanitize_removes_json_leaks()
test_to_json_preserves_unicode()
```

### PromptEngineer (Unit + Integration)
```
test_build_prompt_evidence_mode()
test_build_prompt_includes_grounding_rules()
test_retrieve_constitutional_examples()
test_format_examples_matches_prompt()
```

### CRAGEvaluator (Unit + Integration)
```
test_evaluate_grades_documents()
test_self_reflection_generates_thought_chain()
test_early_return_on_low_evidence()
test_insufficient_evidence_refusal_evidence_mode()
```

### ChatModeHandler (Unit)
```
test_process_chat_no_retrieval()
test_chat_uses_prompt_engineer()
```

### Integration (Full Pipeline)
```
test_orchestrator_with_extracted_services()
test_streaming_with_extracted_services()
test_crag_path_end_to_end()
test_chat_mode_end_to_end()
```

---

## 7. Migration Checklist

- [ ] Phase 1: ResponseSanitizer (30 min)
- [ ] Phase 2: PromptEngineer (2 hours)
- [ ] Phase 3: CRAGEvaluator (2 hours)
- [ ] Phase 4: ChatModeHandler (1 hour)
- [ ] Integration tests pass
- [ ] Code review (focus: initialization order)
- [ ] Merge to main

---

## 8. Files to Modify

### New Files (4)
- `backend/app/utils/response_sanitizer.py` (50 lines)
- `backend/app/services/prompt_engineer.py` (421 lines)
- `backend/app/services/crag_evaluator.py` (250 lines)
- `backend/app/services/chat_handler.py` (80 lines)

### Modified Files (1)
- `backend/app/services/orchestrator_service.py` (2517 → 1870 lines)
- Add 4 imports
- Add 4 injected services to __init__
- Remove 8 methods
- Update 8 method calls

### Documentation
- Update `docs/architecture-map.md` (service sizes)

---

**Status**: Ready for implementation  
**Estimated Effort**: 5-6 hours  
**Risk Level**: Low-Medium (test coverage critical)  
**Backwards Compatibility**: ✅ Fully compatible
