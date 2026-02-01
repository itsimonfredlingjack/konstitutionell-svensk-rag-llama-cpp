# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Swedish RAG system for government documents (1M+ indexed docs from Riksdagen, SFS, Swedish government). FastAPI backend with CRAG pipeline (LangGraph), React + Three.js frontend. Runs on RTX 4070 (12GB VRAM).

## Commands

```bash
# Backend
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8900
systemctl --user start constitutional-ai-backend   # Production

# Frontend (THE ONLY FRONTEND - never create new frontend apps or use Streamlit)
cd apps/constitutional-retardedantigravity
npm run dev -- --port 3001 --host 0.0.0.0

# Full system (llama-server + backend + frontend)
./start_system.sh

# Testing (from backend/)
cd backend
pytest tests/ -v                              # All tests
pytest tests/test_file.py -v                  # Single file
pytest tests/test_file.py::test_function -v   # Single test
pytest -k "test_search" -v                    # Pattern match

# Lint (run from repo root)
ruff check . --fix && ruff format .

# Health check
curl -s http://localhost:8900/api/constitutional/health | jq .
```

## Architecture

### Three Services

| Service | Port | What |
|---------|------|------|
| llama-server (llama.cpp, NOT Ollama) | 8080 | LLM inference, OpenAI-compatible API |
| Backend API (FastAPI) | 8900 | RAG pipeline, all business logic |
| Frontend (React + Vite) | 3001 | `apps/constitutional-retardedantigravity/` |

### Inference: llama.cpp with Speculative Decoding

- **Primary model**: Mistral-Nemo-Instruct-2407 (Q5_K_M) - generation
- **Draft model**: Qwen2.5-0.5B (Q8_0) - speculative decoding
- **Grading model**: Qwen2.5-0.5B (Q5_K_M) - CRAG document relevance
- Config: `start_system.sh` (runtime), `backend/app/services/config_service.py` (all thresholds/models)

### RAG Pipeline Data Flow

```
Query → FastAPI → OrchestratorService → RetrievalOrchestrator (EPR + RAG-Fusion) → ChromaDB
  → BGE Reranker (score threshold + top-N filter) → GraderService/CRAG (Qwen 0.5B)
  → LLMService → llama-server → Mistral-Nemo → Critic→Revise
  → GuardrailService → Response with sources
```

Key pipeline features: EPR intent-based routing with RAG-Fusion multi-query (RRF merge, k=45), BGE reranker-v2-m3 **before** LLM generation (score threshold 0.1, top-5 filter), CRAG document grading (enabled by default), Critic→Revise loop, intent-specific answer contracts, SFS/PRIORITET legal statute prioritization.

### Embeddings

BAAI/bge-m3 (1024 dimensions, hybrid dense+sparse). All ChromaDB collection names end with `_bge_m3_1024` - using wrong suffix causes dimension mismatch errors.

### ChromaDB

Location: `chromadb_data/` (~16GB, git-excluded). Three collections totaling 1,075,956 documents.

## API

There is NO `/search` endpoint. Use `/agent/query` for search.

- `POST /api/constitutional/agent/query` - RAG query (sync)
- `POST /api/constitutional/agent/query/stream` - RAG query (SSE streaming)
- `GET /api/constitutional/health` - Health check
- Full docs: `http://localhost:8900/docs`

## Code Style

- **Python**: ruff (line-length 100, double quotes, `py310` target). Type hints required on function signatures. `B008` ignored (FastAPI `Depends`).
- **TypeScript**: ESLint, functional components, TailwindCSS.
- **Commits**: Conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- **pytest**: `asyncio_mode = "auto"`. Markers: `integration`, `unit`, `slow`, `ollama`.

## Environment Variables

Prefix: `CONST_`. Key vars: `CONST_PORT` (8900), `RAG_SIMILARITY_THRESHOLD` (0.5), `CONST_CRAG_ENABLED`, `CONST_LOG_LEVEL`.

## Common Gotchas

- Verify ports are free before starting services: `lsof -i :8080 :8900 :3001`
- Collection names MUST use `_bge_m3_1024` suffix or you get dimension mismatch
- `config_service.py` has 32K context default but `start_system.sh` overrides to 16,384 at runtime
- Search returning nothing? Lower `RAG_SIMILARITY_THRESHOLD` from 0.5
- Frontend CORS issues? Check port config in `backend/app/config.py`
