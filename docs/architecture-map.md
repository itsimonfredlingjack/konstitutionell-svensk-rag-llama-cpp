# Constitutional AI Architecture Map

**Project**: Swedish Legal Document RAG System  
**Base Path**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/`  
**Framework**: FastAPI 0.109+ (Python 3.12) + React 19 + TypeScript  
**Key Infrastructure**: ChromaDB, llama-server (llama.cpp), LangChain, XState (frontend)

---

## 1. Project Structure

### Root Layout
```
09_CONSTITUTIONAL-AI/
├── backend/              # FastAPI Python backend (13,196 lines of service code)
│   ├── app/
│   │   ├── main.py                    # FastAPI app setup, lifespan, routing
│   │   ├── config.py                  # Pydantic settings (environment vars)
│   │   ├── services/                  # Core business logic (2517+1357+2305 lines in top 3)
│   │   ├── api/                       # REST API routes (472+736 lines)
│   │   ├── core/                      # Exception handlers, custom exceptions
│   │   ├── shared/                    # Shared models/utilities
│   │   └── utils/                     # Logging, metrics
│   └── venv/                          # Python virtualenv (with installed packages)
├── apps/
│   └── constitutional-retardedantigravity/  # React+TypeScript frontend
│       ├── src/
│       │   ├── App.tsx                # Root component
│       │   ├── components/            # UI components (3695 TS/TSX files across project)
│       │   │   ├── 3d/               # WebGL 3D visualization (3 components)
│       │   │   ├── ui/               # Query, results, sources, citations UI
│       │   │   └── ErrorBoundary.tsx
│       │   ├── stores/               # Zustand state management
│       │   ├── constants.ts          # App-wide constants
│       │   └── theme/                # Color system
│       └── dist/                      # Production build output
├── indexers/                          # Data ingestion scripts (23 Python files)
│   └── [index_*.py, migrate_*.py, verify_*.py]
├── scripts/                           # Utility and automation scripts
├── docs/                              # Documentation (50+ markdown files)
├── docker/                            # Docker configuration
├── systemd/                           # Systemd service definitions
├── package.json                       # Workspace package manager (Tailwind, TypeScript)
└── requirements.txt                   # Python dependencies

```

### Key External Dependencies
- **Vector DB**: ChromaDB (local embeddings, cosine similarity)
- **LLM**: llama-server (llama.cpp, OpenAI-compatible API on port 8080) with optional Ollama fallback
- **RAG Framework**: LangChain (chains, tools, agents)
- **Graph Processing**: LangGraph (agentic flow state machine)
- **Embeddings**: BGE-M3 v2/v3 (multi-lingual, dense+sparse)
- **Search**: BM25 (sparse text retrieval)
- **Frontend State**: Zustand, XState (missionControlMachine in some docs)
- **Visualization**: Three.js (3D source viewer)

---

## 2. Data Flow & Pipeline

### User Query → Response (Simplified)

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend (React @ localhost:5173)                               │
│ - QueryBar (user enters question)                               │
│ - Sends POST /api/constitutional/agent/query (AgentQueryRequest)│
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ FastAPI Backend (uvicorn @ 8000/8900)                           │
│ - Router: constitutional_routes.py                              │
│ - Endpoint: POST /agent/query (agent_query)                     │
│ - Routes to: OrchestratorService.process_query()               │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  ┌──────────────────┐      ┌──────────────────────┐
  │ INTENT ROUTING   │      │ QUERY REWRITING      │
  │ (intent_classifier│      │ (query_rewriter.py)  │
  │  intent_routing)  │      └──────────────────────┘
  └──────────────────┘
        │                           │
        └──────────┬────────────────┘
                   ▼
    ┌──────────────────────────────────────┐
    │ MULTI-STRATEGY RETRIEVAL             │
    │ (RetrievalOrchestrator)              │
    │ - RAG Fusion (multiple queries)      │
    │ - Adaptive search (routing engine)   │
    │ - BM25 + Dense embedding search      │
    └──────────┬───────────────────────────┘
               ▼
    ┌──────────────────────────────────────┐
    │ GUARDRAILS & VALIDATION              │
    │ (guardrail_service.py)               │
    │ - Security checks                    │
    │ - Confidence scoring                 │
    │ - Evidence grading                   │
    └──────────┬───────────────────────────┘
               ▼
    ┌──────────────────────────────────────┐
    │ LLM GENERATION                       │
    │ (llm_service.py)                     │
    │ - System prompt building             │
    │ - Context window management          │
    │ - Streaming or batch responses       │
    └──────────┬───────────────────────────┘
               ▼
    ┌──────────────────────────────────────┐
    │ RESPONSE FORMATTING & CITATIONS      │
    │ (structured_output_service.py)       │
    │ - Link claims to sources             │
    │ - Format as AgentQueryResponse       │
    └──────────┬───────────────────────────┘
               │
               ▼
    Return JSON response (answer, sources, citations, evidence_level)
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│ Frontend Display                                                │
│ - AnswerWithCitations component                                 │
│ - SourcesPanel (side panel)                                     │
│ - ThoughtChain or PipelineVisualizer (process steps)           │
└─────────────────────────────────────────────────────────────────┘
```

### Streaming Variant (WebSocket)

- Endpoint: `/ws/harvest` or POST `/agent/query/stream`
- Returns Server-Sent Events (SSE) with `RuntimeEvent` discriminated unions
- Allows real-time progress updates (retrieval phase, grading phase, generation)

---

## 3. Backend Service Architecture

### Service Layer (backend/app/services/)

| Service | Lines | Purpose | Dependencies |
|---------|-------|---------|--------------|
| **orchestrator_service.py** | 2517 | **PRIMARY ORCHESTRATOR** — coordinates entire RAG pipeline, calls all other services | All services, LangGraph |
| **retrieval_orchestrator.py** | 1357 | **RETRIEVAL COORDINATOR** — manages multi-strategy search (fusion, adaptive, routing) | ChronaDB, BM25, embeddings |
| **retrieval_service.py** | 883 | Low-level retrieval (semantic search, BM25, metadata filtering) | ChromaDB client |
| **graph_service.py** | 740 | LangGraph integration for agentic flows (state machine builder) | LangGraph, LLM service |
| **llm_service.py** | 705 | LLM calls via llama-server (OpenAI-compatible API), token counting | httpx, LangChain, OpenAI-compatible client |
| **rag_fusion.py** | 629 | Query expansion & fusion (re-rank diverse results) | Embedding service, retrieval |
| **guardrail_service.py** | 607 | Safety gates (security, hallucination detection) | LLM, confidence signals |
| **confidence_signals.py** | 595 | Evidence scoring, source reliability metrics | BM25, embeddings |
| **query_rewriter.py** | 539 | Query enhancement & sub-query generation | Embedding service, LLM |
| **grader_service.py** | 529 | CRAG grading (is answer correct? need web search?) | LLM, retrieval |
| **critic_service.py** | 522 | Response critic (hallucination detection) | LLM, confidence signals |
| **query_processor_service.py** | 529 | Input validation, preprocessing, intent detection | Intent classifier |
| **intent_classifier.py** | 403 | Intent routing (is this a question vs. claim?) | LLM, query processor |
| **config_service.py** | 424 | Configuration management (dynamic settings) | Pydantic |
| **swedish_compound_splitter.py** | 477 | Swedish linguistic preprocessing | NLTK, regex |
| **bm25_service.py** | 271 | BM25 indexing & sparse text search | rank-bm25 library |
| **structured_output_service.py** | 258 | JSON response formatting, schema validation | Pydantic |
| **reranking_service.py** | 356 | Cross-encoder reranking of retrieved results | LangChain, embeddings |
| **embedding_service.py** | 209 | Embedding generation (BGE-M3) | ChromaDB, embeddings |
| **intent_routing.py** | 170 | Router dispatch based on intent | Services |
| **base_service.py** | 127 | Abstract base class for all services | — |
| **sse_stream_service.py** | 37 | Server-Sent Events stream handling | FastAPI |
| **legal_abbreviations.py** | 273 | Swedish legal term expansion (SOU, DS, etc.) | Regex |
| **source_hierarchy.py** | 39 | Source priority ranking | Enums |

**Total**: 13,196 lines across 25 service files

### Design Patterns
- **Service Locator**: `get_orchestrator_service()`, `get_llm_service()` singleton getters
- **Dependency Injection**: FastAPI `Depends()` for route handlers
- **State Management**: Orchestrator maintains pipeline metrics and call history
- **Async Throughout**: All I/O is asyncio-based (httpx, ChromaDB async API)

---

## 4. API Routes

### File: `backend/app/api/constitutional_routes.py` (472 lines)

| Method | Endpoint | Request Model | Response Model | Validation | Notes |
|--------|----------|---------------|----------------|-----------|-------|
| GET | `/health` | — | `HealthResponse` | — | Service health check |
| GET | `/metrics` | — | RAG metrics dict | — | Pipeline performance stats |
| GET | `/metrics/prometheus` | — | Prometheus format | — | Monitoring export |
| GET | `/stats/overview` | — | `OverviewStats` | — | Document counts, storage |
| GET | `/collections` | — | List[`CollectionInfo`] | — | ChromaDB collections |
| POST | `/agent/query` | `AgentQueryRequest` | `AgentQueryResponse` | ✓ min/max length | Main search endpoint |
| POST | `/agent/query/stream` | `AgentQueryRequest` | Server-Sent Events | ✓ same as above | Streaming variant |
| WS | `/ws/harvest` | — | WebSocket frames | — | Live indexing progress |

**Input Validation**:
- `question`: 1–2000 chars ✓
- `history`: max 10 messages ✓
- `mode`: enum ("auto", "chat", "assist", "evidence") ✓
- `use_agent`: boolean flag ✓

**Response Validation**: All responses structured as Pydantic models ✓

### File: `backend/app/api/document_routes.py` (736 lines)

| Method | Endpoint | Request Model | Response Model | Validation | Notes |
|--------|----------|---------------|----------------|-----------|-------|
| GET | `/documents` | query params (filters, page, limit) | Paginated document list | ✓ sanitize input | List documents with metadata |
| GET | `/documents/{doc_id}` | — | Document detail | — | Single document fetch |
| POST | `/documents` | Document model | Created document | ✓ validate schema | Create new document |
| PUT | `/documents/{doc_id}` | Document model | Updated document | ✓ validate schema | Replace document |
| PATCH | `/documents/{doc_id}` | Partial fields | Updated document | ✓ validate fields | Partial update |
| DELETE | `/documents/{doc_id}` | — | Success response | — | Remove document |

**Input Sanitization**: `sanitize_input()` for text fields (max 10k chars) ✓

**Total API Endpoints**: 13 (5 health/metrics, 8 document CRUD + search, 1 WebSocket)

---

## 5. Frontend Architecture

### Technology Stack
- **Framework**: React 19
- **Language**: TypeScript 5.9
- **Styling**: Tailwind CSS 4.1 + PostCSS
- **State**: Zustand (useAppStore)
- **3D Visualization**: Three.js
- **UI Patterns**: Component-based with error boundaries

### Component Structure

```
src/
├── App.tsx                              # Root container
├── components/
│   ├── 3d/
│   │   ├── SourceViewer3D.tsx          # 3D source document viewer
│   │   ├── Substrate.tsx               # 3D background/substrate
│   │   └── ConnectorLogic.tsx          # Edge rendering between sources
│   ├── ui/
│   │   ├── QueryBar.tsx                # Input field for user question
│   │   ├── ResultsSection.tsx          # Main answer display area
│   │   ├── SourcesPanel.tsx            # Retrieved document sidebar
│   │   ├── AnswerWithCitations.tsx     # Answer + inline citations
│   │   ├── CitationPreview.tsx         # Tooltip on citation hover
│   │   ├── citations.ts                # Citation utilities
│   │   ├── ThoughtChain.tsx            # Show reasoning steps
│   │   ├── PipelineVisualizer.tsx      # Show RAG phases (retrieval→grade→gen)
│   │   ├── SearchOverlay.tsx           # Loading overlay
│   │   ├── HeroSection.tsx             # Welcome screen
│   │   ├── QueryProcessor.tsx          # Process status
│   │   ├── ConnectorOverlay.tsx        # Connect sources visually
│   │   └── TrustHull.tsx               # Trust/confidence visualization
│   └── ErrorBoundary.tsx               # Error fallback UI
├── stores/
│   └── useAppStore.ts                  # Zustand store (query state, results, UI state)
├── constants.ts                        # API URLs, timeouts, etc.
├── theme/
│   └── colors.ts                       # Color palette (glassmorphism)
├── main.tsx                            # Entry point
└── App.css                             # Global styles
```

### Data Flow (Frontend)
1. User types in `QueryBar` → updates Zustand store
2. Submit → `App.tsx` calls `POST /api/constitutional/agent/query`
3. Response → store updated with `AgentQueryResponse`
4. Components re-render:
   - `ResultsSection` shows answer
   - `SourcesPanel` lists retrieved documents
   - `PipelineVisualizer` shows query routing
   - 3D components render source connections

---

## 6. Dependencies & External Services

### Runtime Dependencies (Python)
```
fastapi>=0.109.0                      # Web framework
uvicorn[standard]>=0.27.0             # ASGI server
httpx>=0.26.0                         # Async HTTP client (for llama-server LLM calls)
pydantic>=2.5.0                       # Data validation
pydantic-settings>=2.1.0              # Environment config
websockets>=12.0                      # WebSocket support
anyio>=4.2.0                          # Async utilities
psutil>=5.9.0                         # System monitoring
python-dotenv>=1.0.0                  # Environment loading
```

### External Services (Runtime)
| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| **ChromaDB** | (embedded) | Vector database (local) | Always on |
| **llama-server** | 8080 | Local LLM (llama.cpp, OpenAI-compatible) | Primary |
| **Ollama** | 11434 | Local LLM fallback | Optional (legacy) |
| **llama-server** | 8080 | Local LLM (llama.cpp, OpenAI-compatible) | Primary |
| **Qdrant** (historical) | 6333 | Vector DB (legacy, being phased out) | Deprecated |

### Frontend Dependencies (npm)
```
@tailwindcss/postcss>=4.1.18           # CSS framework
typescript>=5.9.3                      # Type checking
@types/node>=25.0.6                    # Node types
```

---

## 7. Key Decomposition Points & Tech Debt

### Critical Large Components

#### 1. **orchestrator_service.py (2517 lines)**
   - **Problem**: Monolithic orchestrator handling too many responsibilities
   - **Responsibilities**:
     - RAG pipeline coordination
     - CRAG grading logic
     - LLM context building
     - Constitutional examples retrieval
     - System prompt engineering
     - Answer sanitization
     - Streaming and batch processing
   - **Extractable modules** (see Task #2 for full analysis):
     1. **CRAGEvaluator** — grading logic → separate service
     2. **PromptEngineer** — system prompt, context building → utility
     3. **ConstitutionalExamples** — example retrieval → separate service
     4. **ResponseSanitizer** — answer validation → utility
     5. **PipelineMetrics** — telemetry → metrics service

#### 2. **retrieval_orchestrator.py (1357 lines)**
   - **Problem**: Complex multi-strategy retrieval with nested function definitions
   - **Extractable**:
     - RAG Fusion module
     - Adaptive routing engine
     - Routing policy service

#### 3. **llm_service.py (705 lines)**
   - **Dual responsibility**: LLM calls + token counting
   - **Extractable**: TokenCounter as separate utility

### Dead Code & Cleanup Targets
- `/archive/` directory — legacy search implementations
- Qdrant migration code (chromadb_to_qdrant.py) — can remove post-migration
- Old indexers with duplicate logic
- Historical benchmark scripts (rag_benchmark.py)

### Configuration Scatter
- Hardcoded values in service constructors (should be in config_service.py)
- Magic numbers for timeouts, retry counts
- Embedding model names scattered across files

---

## 8. Data Storage & Indexing

### ChromaDB Collections
Collection names (document types):
- `naturvardsverket` (environmental authority docs)
- `socialstyrelsen` (social board docs)
- `kemi` (chemical safety docs)
- `jk` (justice council)
- `prv` (patents & trademarks)
- `folkhalsomyndigheten` (public health authority)
- `arn` (labor court)
- `vr` (veterinary board)
- ... (20+ more domain-specific collections)

### Indexing Pipeline
```
Raw documents (PDF/JSON) 
    → indexers/*.py (extract, clean, chunk)
    → Embed with BGE-M3
    → Index to ChromaDB
    → BM25 index for sparse search
    → Verify (verify_*.py scripts)
    → Optional: Migrate to new embedding model (migrate_*.py)
```

---

## 9. Configuration & Environment

### Config Sources (in order of precedence)
1. Environment variables (`CONST_*` prefix)
2. `.env` file
3. Pydantic defaults in `config.py`

### Key Settings
| Variable | Default | Purpose |
|----------|---------|---------|
| `CONST_HOST` | 0.0.0.0 | Server bind address |
| `CONST_PORT` | 8900 | Server port |
| `CONST_LLM_BASE_URL` | http://localhost:8080/v1 | LLM endpoint (OpenAI-compatible) |
| `CONST_OLLAMA_BASE_URL` | http://localhost:11434 | Ollama fallback |
| `CONST_CRAG_ENABLED` | False | Enable CRAG grading |
| `CONST_LOG_LEVEL` | INFO | Logging level |
| `CONST_CORS_ORIGINS` | [localhost:*] | Allowed frontend domains |

---

## 10. Execution & Deployment

### Development
```bash
# Start backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Start frontend
cd apps/constitutional-retardedantigravity
npm install
npm run dev  # Vite dev server on :5173
```

### Docker Deployment
- Dockerfiles in `docker/` directory
- Systemd services in `systemd/` for production

### Health Endpoints
- `GET /health` → OrchestratorService.health_check()
- `GET /` → Basic server info

---

## 11. Testing & Quality Assurance

### Test Coverage Status
- Backend: ~11 test files
- Frontend: No test runner configured (Vitest/Jest needed)
- Missing: Integration tests for full RAG pipeline

### Key Testing Gaps
- E2E tests for query→answer flow
- ChromaDB persistence tests
- LLM fallback behavior tests
- CORS policy validation
- Streaming response tests

---

## 12. Security & Compliance

### Current Protections
- **CORS**: Explicit whitelist in config ✓
- **Input Validation**: Pydantic models on all API routes ✓
- **Error Handling**: Custom exception handlers (no stack trace leaks) ✓
- **Logging**: Structured logging with metrics ✓

### Audit Findings (See Task #4)
- No authentication/authorization (public API)
- No rate limiting
- No request size limits (except input sanitization)
- ChromaDB credentials: hardcoded paths (acceptable for local)

---

## 13. Dependency Graph Summary

### Service Call Chain (Simplified)
```
OrchestratorService (main coordinator)
├── RetrievalOrchestrator (multi-strategy search)
│   ├── RetrievalService (ChromaDB queries)
│   ├── BM25Service (sparse search)
│   └── RerankingService (cross-encoder)
├── QueryProcessor (input validation)
├── QueryRewriter (sub-query generation)
├── IntentClassifier (routing decision)
├── GuardrailService (safety checks)
│   └── ConfidenceSignals (evidence scoring)
├── LLMService (llm calls)
├── GraderService (CRAG evaluation)
├── CriticService (hallucination detection)
├── StructuredOutputService (JSON formatting)
└── ConfigService (dynamic settings)
```

### Frontend Dependencies
```
App.tsx (root)
├── QueryBar (input)
├── ResultsSection
│   ├── AnswerWithCitations
│   │   └── CitationPreview
│   └── ThoughtChain
├── SourcesPanel
├── PipelineVisualizer
├── 3D Components
│   ├── SourceViewer3D
│   ├── Substrate
│   └── ConnectorLogic
└── ErrorBoundary
```

---

## 14. Key Files Reference

| Path | Purpose | Owner |
|------|---------|-------|
| `backend/app/main.py` | FastAPI app, lifespan, routing | Backend lead |
| `backend/app/services/orchestrator_service.py` | Pipeline orchestration | AI team (needs decomposition) |
| `backend/app/services/retrieval_orchestrator.py` | Multi-strategy retrieval | Retrieval team |
| `backend/app/api/constitutional_routes.py` | Query & health endpoints | API team |
| `backend/app/api/document_routes.py` | Document CRUD endpoints | Data team |
| `apps/constitutional-retardedantigravity/src/App.tsx` | Frontend root | UI team |
| `backend/app/config.py` | Environment settings | DevOps |
| `docs/` | Architecture & decision logs | Team |

---

## 15. Next Steps for Architecture Improvement

1. **Refactor OrchestratorService** (2517 → ~600 lines):
   - Extract CRAG evaluator
   - Extract prompt engineer
   - Extract response sanitizer
   - Keep orchestrator for coordination only

2. **Consolidate Retrieval Logic**:
   - Merge RetrievalOrchestrator and RetrievalService
   - Simplify routing engine

3. **Add Tests**:
   - Integration tests for full RAG flow
   - Frontend test suite (Vitest)
   - Streaming response tests

4. **Observability**:
   - Distributed tracing (OpenTelemetry)
   - RAG-specific metrics dashboard
   - Error rate monitoring

5. **Documentation**:
   - API spec as OpenAPI/Swagger
   - Data flow diagrams in docs/
   - Runbook for indexing new collections

---

**Document Generated**: 2025-02-07  
**Status**: Architecture analysis complete - ready for decomposition tasks
