# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Constitutional AI is a RAG system for Swedish government documents (1.37M+ documents: 538K legal/gov + 829K DiVA research across Riksdagen, municipalities, and government agencies). It uses ChromaDB with BAAI/bge-m3 embeddings (1024 dims) for semantic search, llama-server (llama.cpp) for local LLM inference, a FastAPI backend on port 8900, and a React+Vite+Three.js frontend on port 3001. CRAG is enabled (self-reflection + grading active).

This is an independent git repository nested at `AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/`.

## Development Commands

### Backend (port 8900)

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Tests
pytest tests/ -v                          # all tests
pytest tests/test_constitution.py -v      # single file
pytest tests/test_constitution.py::test_name  # single test
pytest -m unit                            # unit tests only (no network/GPU)
pytest -m "not slow"                      # skip slow tests

# Integration/Ollama tests are opt-in:
RUN_INTEGRATION_TESTS=1 pytest -m integration
RUN_OLLAMA_TESTS=1 pytest -m ollama

# Lint & format
ruff check .
ruff check --fix .
ruff format .
```

### Frontend (port 3001)

**The only real frontend is `apps/constitutional-retardedantigravity/`.** Never create new frontend apps. Ignore any `/frontend/` directory.

```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev       # dev server on :3001
npm run build     # tsc -b && vite build
npm run lint      # eslint
```

The frontend connects to `VITE_BACKEND_URL` (defaults to `http://localhost:8900`).

### Systemd Services

```bash
systemctl --user status constitutional-ai-backend
systemctl --user restart constitutional-ai-backend
journalctl --user -u constitutional-ai-backend -f
```

Never restart services without explicit user permission. Always check `lsof -i :PORT` before starting anything.

### Health Check / Quick Test

```bash
curl http://localhost:8900/api/constitutional/health | jq .

# RAG query
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Vad säger GDPR om personuppgifter?","mode":"assist"}' | jq .
```

API docs: `http://localhost:8900/docs` (Swagger) and `/redoc`.

## Architecture

### RAG Pipeline

```
User Query → Frontend → POST /api/constitutional/agent/query/stream
  → OrchestratorService
    → IntentClassifier (classifies query type)
    → QueryRewriter (rewrites/expands query for better retrieval)
    → RetrievalOrchestrator → RetrievalService → ChromaDB (1.37M+ docs)
    → GraderService (grades document relevance)
    → LLMService → llama-server (Mistral-Nemo-Instruct-2407-Q5_K_M.gguf)
    → GuardrailService (blocks hallucinated answers in EVIDENCE mode)
  → Streaming SSE response → Frontend
```

Three query modes with different LLM parameters:
- **EVIDENCE** (temp 0.2): Strict source-grounded answers from the corpus
- **ASSIST** (temp 0.4): Guided help using sources as context
- **CHAT** (temp 0.7): Conversational, less strict

### Backend Service Layer (`backend/app/services/`)

The orchestrator (`orchestrator_service.py`, ~108KB) is the central coordinator. Key services:

| Service | Purpose |
|---------|---------|
| `orchestrator_service.py` | Main RAG pipeline coordinator |
| `retrieval_service.py` | ChromaDB vector search |
| `retrieval_orchestrator.py` | Advanced multi-strategy retrieval |
| `llm_service.py` | llama-server (OpenAI-compatible) integration with streaming |
| `embedding_service.py` | BAAI/bge-m3 embeddings (1024 dims) |
| `graph_service.py` | LangGraph state machine for CRAG |
| `guardrail_service.py` | Hallucination detection, safety checks |
| `intent_classifier.py` | Query type classification |
| `query_rewriter.py` | Query expansion/reformulation |
| `grader_service.py` | Document relevance grading |
| `bm25_service.py` | Sparse keyword retrieval |
| `rag_fusion.py` | Multi-query result fusion |
| `source_hierarchy.py` | SFS > prop/SOU source prioritization |

Services are singletons obtained via `get_*_service()` factory functions.

### Frontend Architecture (`apps/constitutional-retardedantigravity/`)

React 19 + Vite 7 + TypeScript 5.9 + Three.js (React Three Fiber/Drei) + Tailwind CSS 4 + Zustand.

- `src/App.tsx` — Main app with 3D canvas background
- `src/stores/useAppStore.ts` — Zustand store; manages query state, streaming SSE consumption, pipeline visualization
- `src/components/3d/` — Three.js 3D visualization components
- `src/components/ui/` — UI components (HeroSection, ResultsSection, SourcesPanel, PipelineVisualizer, TrustHull)

### API Routes

All routes prefixed with `/api/constitutional` (defined in `backend/app/api/constitutional_routes.py`):

- `GET /health` — Health check
- `GET /stats/overview` — Collection statistics
- `GET /collections` — List ChromaDB collections
- `POST /agent/query` — RAG query (JSON response)
- `POST /agent/query/stream` — RAG query (SSE streaming, used by frontend)
- `POST /search` — Document search
- `WS /ws/harvest` — Live harvest progress WebSocket

### Configuration

Backend settings in `backend/app/config.py` via pydantic-settings. Environment variables prefixed with `CONST_` (e.g., `CONST_DEBUG=true`, `CONST_LOG_LEVEL=DEBUG`). Loads `.env` automatically.

Key settings: `CONST_CRAG_ENABLED`, `CONST_OLLAMA_BASE_URL`, `CONST_LLM_BASE_URL`.

## Code Style

### Python

Ruff: line-length 100, target py310. Configured in `pyproject.toml`. All functions require type hints. Import order: stdlib → third-party → local. Pytest: `asyncio_mode = "auto"`.

### TypeScript/React

Functional components only. Use `import type` for type-only imports. Tailwind CSS with `clsx`/`tailwind-merge` for conditional classes. Zustand for state management.

### Commits

Conventional commits: `feat(scope): description`, `fix(scope): description`, etc.

## Data

- **ChromaDB**: `chromadb_data/` (~15GB, excluded from git)
- **Collections** (all suffixed with `_bge_m3_1024`): `swedish_gov_docs_bge_m3_1024` (304K docs), `riksdag_documents_p1_bge_m3_1024` (230K docs), DiVA research collections (829K docs)
- **Total Documents**: 1.37M+ (538K legal/gov + 829K DiVA research)
- **Embeddings**: BAAI/bge-m3 (1024 dimensions)
- **Reranker**: BAAI/bge-reranker-v2-m3
- **LLM models**: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf (primary), gpt-sw3-6.7b-v2-instruct-Q5_K_M.gguf (fallback) via llama-server on port 8080
- **CRAG**: Enabled (self-reflection + grading active)

## Guardrails for AI Agents

- **Never** modify `constitutional_routes.py`, systemd files, or model parameters without asking first
- **Never** use Playwright/Selenium without explicit permission
- **Never** delete ChromaDB data
- **Always** do route discovery (grep routes, check OpenAPI) before claiming an endpoint doesn't exist
- Model parameter changes must be documented in `docs/MODEL_OPTIMIZATION.md`
- System prompt changes must be tested with diverse queries before deployment
