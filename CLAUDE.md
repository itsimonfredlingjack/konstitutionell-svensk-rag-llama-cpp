# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Swedish RAG (Retrieval-Augmented Generation) system for government documents with 538K+ indexed documents from Riksdagen and Swedish government sources. FastAPI backend with agentic LLM pipeline (LangGraph), React + TypeScript + Three.js frontend.

## Build & Run Commands

### Backend (port 8900)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Or use systemd (production)
systemctl --user start constitutional-ai-backend
systemctl --user status constitutional-ai-backend
journalctl --user -u constitutional-ai-backend -f
```

### Frontend (port 3001)
```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev -- --port 3001 --host 0.0.0.0
npm run build      # Production build
npm run lint       # ESLint
```

### Testing
```bash
# Python
cd backend
pytest tests/ -v                                  # All tests
pytest tests/test_file.py -v                      # Single file
pytest tests/test_file.py::test_function -v       # Single function
pytest -k "test_search" -v                        # Pattern match
pytest -m "unit" -v                               # Marker match

# Linting
ruff check .              # Check
ruff check --fix .        # Auto-fix
ruff format .             # Format
```

### Health Check
```bash
curl http://localhost:8900/api/constitutional/health | jq .
```

## Architecture

### Backend Services (backend/app/services/)
Service-oriented architecture with 18+ specialized services:
- **OrchestratorService** - Main RAG pipeline orchestration
- **RetrievalOrchestrator/RetrievalService** - Multi-strategy ChromaDB search
- **LLMService** - Ollama integration (ministral-3:14b)
- **GraphService** - LangGraph state machine for agentic flows
- **GraderService** - RAG document relevance grading
- **CriticService** - CRAG (Corrective RAG) critique & revision
- **GuardrailService** - Response safety filtering
- **ConfidenceSignals** - Answer confidence scoring

### API Routes (backend/app/api/)
- `GET /api/constitutional/health` - Health check
- `GET /api/constitutional/stats/overview` - Statistics
- `POST /api/constitutional/search` - Document search
- `POST /api/constitutional/agent/query` - RAG query (sync)
- `POST /api/constitutional/agent/query/stream` - RAG query (streaming)

### Frontend (apps/constitutional-retardedantigravity/)
React + Vite + TypeScript + TailwindCSS + Three.js
- **UI Components** (`src/components/ui/`) - Search interface, results, pipeline visualization
- **3D Components** (`src/components/3d/`) - Three.js source visualization
- **State Management** (`src/stores/useAppStore.ts`) - Zustand store
- **API Client** (`src/services/api.ts`)

### Data Flow
```
User Query → FastAPI (8900) → OrchestratorService
    → RetrievalService → ChromaDB (538K docs)
    → GraderService → CriticService (CRAG)
    → LLMService → Ollama (11434)
    → Response with sources
```

## Configuration

### Environment Variables (prefix: CONST_)
- `CONST_PORT` - Backend port (default 8900)
- `CONST_OLLAMA_BASE_URL` - Ollama endpoint (default http://localhost:11434)
- `CONST_CRAG_ENABLED` - Enable Corrective RAG pipeline
- `CONST_LOG_LEVEL` - Logging level

### Code Style
- Python: ruff (line length 100, double quotes), type hints required
- TypeScript: ESLint, functional components, Tailwind CSS

## Critical Guardrails

### READ FIRST
- `.cursorrules` - Frontend guardrails (Swedish/English)
- `AGENTS.md` - AI agent guidelines
- `FRONTEND_README.md` - Before any frontend work

### Frontend Rules
- **THE ONLY FRONTEND**: `/apps/constitutional-retardedantigravity/` (React + Vite, port 3001)
- **NEVER** create new frontend apps or use Streamlit
- **NEVER** touch `/frontend/` folder (deprecated)

### Service Management
- **ALWAYS** check ports first: `lsof -i :8900`
- **ALWAYS** check systemd: `systemctl --user status constitutional-ai-backend`
- Backend port: **8900** (NOT 8000)

### Data
- `chromadb_data/`, `pdf_cache/`, `backups/` are large (16GB+) and excluded from git
- 538K+ documents indexed across collections

### Code Changes
- **NEVER** guess code behavior - read files first
- Use grep to find related code: `grep -r "@router" backend/app/api/`
- Check endpoints: `curl http://localhost:8900/docs`

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entry point |
| `backend/app/config.py` | Settings (Pydantic + env vars) |
| `backend/app/api/constitutional_routes.py` | Main API routes |
| `backend/app/services/orchestrator_service.py` | Core RAG pipeline |
| `apps/constitutional-retardedantigravity/src/App.tsx` | Frontend root |
| `apps/constitutional-retardedantigravity/src/stores/useAppStore.ts` | Zustand state |
