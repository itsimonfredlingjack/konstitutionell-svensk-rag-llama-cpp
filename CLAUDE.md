# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Swedish RAG system for government documents with **1,075,956 indexed documents** from Riksdagen, SFS (Swedish Code of Statutes), and Swedish government sources. FastAPI backend with agentic LLM pipeline (LangGraph), React + TypeScript + Three.js frontend.

## Ports & Services

| Service | Port | Description |
|---------|------|-------------|
| llama-server | 8080 | LLM inference (OpenAI-compatible API) |
| Backend API | 8900 | FastAPI application |
| Frontend | 3001 | React + Vite |

**Hardware**: RTX 4070 (12GB VRAM) - all optimizations are tuned for this constraint.

## Build & Run Commands

### Backend (port 8900)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Production (systemd)
systemctl --user start constitutional-ai-backend
systemctl --user status constitutional-ai-backend
journalctl --user -u constitutional-ai-backend -f
```

### Frontend (port 3001)
```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev -- --port 3001 --host 0.0.0.0
npm run build      # Production
npm run lint       # ESLint
```

### LLM Server (port 8080)
```bash
./start_system.sh  # Starts llama-server with optimized settings
```

### Testing
```bash
cd backend
pytest tests/ -v                                  # All tests
pytest tests/test_file.py -v                      # Single file
pytest tests/test_file.py::test_function -v       # Single function
pytest -k "test_search" -v                        # Pattern match

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

### Inference Stack (llama.cpp, NOT Ollama)

The system uses **llama-server** (from llama.cpp), not Ollama:

| Component | Value | Config Location |
|-----------|-------|-----------------|
| Backend | llama-server | `start_system.sh` |
| Port | 8080 (OpenAI-compatible) | `start_system.sh:58` |
| Primary Model | Mistral-Nemo-Instruct-2407-Q5_K_M.gguf | `config_service.py:51` |
| Draft Model | Qwen2.5-0.5B-Instruct-Q8_0.gguf | `start_system.sh:6` |
| Grading Model | Qwen2.5-0.5B-Instruct-Q5_K_M.gguf | `config_service.py:145` |

**Optimizations enabled:**
- Speculative Decoding (`--model-draft`) - Qwen 0.5B drafts tokens, Mistral-Nemo validates
- KV-Cache Quantization (`-ctk q8_0 -ctv q8_0`) - 4x memory reduction vs FP16
- Flash Attention (`-fa on`)
- GPU Offloading (`-ngl 60`) - 60 layers on GPU
- Context: 16,384 tokens (runtime via `start_system.sh`; `config_service.py` has 32K default)

### Embeddings (BGE-M3)

| Component | Value |
|-----------|-------|
| Model | BAAI/bge-m3 |
| Dimensions | 1024 |
| Capability | Hybrid search (dense + sparse) |
| Collection Suffix | `_bge_m3_1024` |

Critical for Swedish legal texts where exact terminology matters.

### Backend Services (backend/app/services/)

18 services, ~10K lines total. Key services:

| Service | Purpose |
|---------|---------|
| `orchestrator_service.py` | Main RAG pipeline orchestration (1.9K lines) |
| `retrieval_orchestrator.py` | Adaptive retrieval with 4-step escalation |
| `retrieval_service.py` | ChromaDB search with score threshold filtering |
| `llm_service.py` | Dual backend support (llama-server/Ollama fallback) |
| `graph_service.py` | LangGraph state machine for agentic flows |
| `grader_service.py` | CRAG document relevance grading (Qwen 0.5B) |
| `critic_service.py` | CRAG critique & revision |
| `confidence_signals.py` | 10 weighted signals for retrieval quality |
| `rag_fusion.py` | Multi-query expansion with RRF merging |
| `reranking_service.py` | BGE reranker-v2-m3 cross-encoder |
| `guardrail_service.py` | Response safety filtering |

### RAG Pipeline Optimizations

All implemented and active:
- **Score threshold filtering** (0.5 default) with adaptive fallback
- **O(1) deduplication** preserving highest-scoring version
- **Timeout handling** (5s) with graceful degradation
- **BGE reranker-v2-m3** cross-encoder reranking
- **RRF merging** (k=60) for multi-query fusion
- **SFS/PRIORITET** prioritization for Swedish legal statutes
- **4-step adaptive escalation** (A→B→C→D) with no-answer policy
- **RAG-Fusion** 3-query expansion (semantic, lexical, paraphrase)
- **10 confidence signals** with weighted scoring and abstain threshold

### Data Flow
```
User Query → FastAPI (8900) → OrchestratorService
    → RetrievalOrchestrator → ChromaDB (538K docs)
    → GraderService (Qwen 0.5B) → CriticService (CRAG)
    → LLMService → llama-server (8080) → Mistral-Nemo
    → GuardrailService → Response with sources
```

### Frontend

**THE ONLY FRONTEND**: `apps/constitutional-retardedantigravity/`
- Framework: React 18 + Vite + TypeScript
- Styling: TailwindCSS
- 3D: Three.js (source visualization)
- State: Zustand (`src/stores/useAppStore.ts`)
- API Client: `src/services/api.ts`
- Trust Hull: `src/components/ui/TrustHull.tsx` - confidence visualization
- Streaming: Server-Sent Events (SSE) for real-time response display

## API Routes

- `GET /api/constitutional/health` - Health check
- `GET /api/constitutional/stats/overview` - Statistics
- `GET /api/constitutional/collections` - List collections
- `POST /api/constitutional/agent/query` - RAG query (sync)
- `POST /api/constitutional/agent/query/stream` - RAG query (streaming)

**NOTE**: There is NO `/search` endpoint. Use `/agent/query` for search.

Full docs: `http://localhost:8900/docs`

## Configuration

### Environment Variables (prefix: CONST_)
- `CONST_PORT` - Backend port (default 8900)
- `RAG_SIMILARITY_THRESHOLD` - Score threshold (default 0.5)
- `CONST_CRAG_ENABLED` - Enable Corrective RAG pipeline
- `CONST_LOG_LEVEL` - Logging level

### Key Config Files
- `backend/app/services/config_service.py` - All service settings
- `start_system.sh` - llama-server launch parameters
- `backend/pyproject.toml` - Ruff, pytest config

### Code Style
- Python: ruff (line length 100, double quotes), type hints required
- TypeScript: ESLint, functional components, Tailwind CSS

## Critical Guardrails

### Ports - ALWAYS verify before starting services
```bash
lsof -i :8080   # llama-server
lsof -i :8900   # Backend
lsof -i :3001   # Frontend
```

### Frontend Rules
- **ONLY** use `apps/constitutional-retardedantigravity/`
- **NEVER** create new frontend apps
- **NEVER** use Streamlit

### Data (ChromaDB)
- Location: `chromadb_data/` (~16GB, excluded from git)
- **Total: 1,075,956 documents**

Collections (BGE-M3 1024-dim):
| Collection | Documents |
|------------|-----------|
| swedish_gov_docs_bge_m3_1024 | 304,871 |
| riksdag_documents_p1_bge_m3_1024 | 230,143 |
| sfs_lagtext_bge_m3_1024 | 2,887 |

Migration scripts in `indexers/` include thermal pacing (GPU temp monitoring at 78/83/88°C thresholds).

### Code Changes
- **NEVER** guess code behavior - read files first
- Use grep: `grep -r "@router" backend/app/api/`
- Check endpoints: `curl http://localhost:8900/docs`

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entry point |
| `backend/app/services/config_service.py` | All settings (models, thresholds, etc.) |
| `backend/app/api/constitutional_routes.py` | Main API routes |
| `backend/app/services/orchestrator_service.py` | Core RAG pipeline |
| `backend/app/services/llm_service.py` | LLM integration |
| `start_system.sh` | llama-server launch script |
| `apps/constitutional-retardedantigravity/src/App.tsx` | Frontend root |
| `apps/constitutional-retardedantigravity/src/stores/useAppStore.ts` | Zustand state |

## Agent Awareness

### Useful Global Skills for This Project
| Skill | When to Use |
|-------|-------------|
| `systematic-debugging` | RAG pipeline issues, search quality problems |
| `test-driven-development` | Adding new features to backend services |
| `verification-before-completion` | Before committing changes |
| `webapp-testing` | Frontend debugging with Playwright |

### Quick Health Check
```bash
# All services status
curl -s http://localhost:8900/api/constitutional/health | jq .
curl -s http://localhost:8080/v1/models  # llama-server
lsof -i :3001  # Frontend

# Test RAG query
curl -s -X POST http://localhost:8900/api/constitutional/agent/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "mode": "auto"}' | head -5
```

### Common Issues
| Symptom | Check | Fix |
|---------|-------|-----|
| "dimension mismatch" | Collection names | Use `_bge_m3_1024` suffix |
| Slow inference | GPU utilization | Check `nvidia-smi`, restart llama-server |
| Frontend won't connect | CORS | Verify port in `backend/app/config.py` |
| Search returns nothing | Threshold | Lower `RAG_SIMILARITY_THRESHOLD` from 0.5 |
