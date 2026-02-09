# Constitutional AI - AI Index

> Denna fil är designad för AI-modeller att förstå projektstrukturen snabbt.

## Projektets Syfte

Constitutional AI är ett RAG-system (Retrieval-Augmented Generation) för svenska myndighetsdokument med:
- 1.37M+ dokument (538K legal/gov + 829K DiVA research)
- ChromaDB som vector database
- llama-server (llama.cpp) för lokal LLM-inferens (Ollama som fallback)
- FastAPI backend + React frontend

## Viktiga Filer för AI-förståelse

### 1. Systemöversikt (START HÄR)
**Fil**: `docs/system-overview.md`
**Innehåll**: Arkitektur, services, collections, key files

### 2. Backend Status
**Fil**: `docs/BACKEND_STATUS.md`
**Innehåll**: Service status, endpoints, system commands

### 3. API Dokumentation
**Fil**: `apps/constitutional-dashboard/CONSTITUTIONAL_API.md`
**Innehåll**: Alla API endpoints med exempel

### 4. Modelloptimering
**Fil**: `docs/MODEL_OPTIMIZATION.md`
**Innehåll**: System prompts, modellparametrar, optimering

### 5. Agent Guardrails
**Fil**: `docs/guardrails.md`
**Innehåll**: Regler för AI-agenter som arbetar med projektet

## Kodstruktur

### Backend (`backend/`)
- `app/main.py` - FastAPI application entry point
- `app/api/constitutional_routes.py` - API routes (550+ lines)
- `app/services/orchestrator_service.py` - RAG orchestration
- `app/services/retrieval_service.py` - ChromaDB retrieval
- `app/services/llm_service.py` - llama-server integration (Ollama fallback)

### Frontend (`apps/`)
- `constitutional-gpt/` - Main RAG interface (Next.js 16)
- `constitutional-dashboard/` - Metrics dashboard (Vite + React)

### Scrapers (`scrapers/`)
- ~100 Python-filer för web scraping
- Riksdagen, myndigheter, kommuner

## Data Flow

```
User Query → Frontend → Backend API → Orchestrator
    ↓
Retrieval Service → ChromaDB (1.37M+ docs)
    ↓
LLM Service → llama-server (Mistral-Nemo-Instruct-2407-Q5_K_M.gguf)
    ↓
Response → Frontend → User
```

## Viktiga Konfigurationer

- **ChromaDB Path**: Konfigureras i `backend/app/config.py` (data exkluderas från git)
- **LLM Models**: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf via llama-server (port 8080), gpt-sw3 (fallback)
- **Embedding Model**: BAAI/bge-m3 (1024 dimensions)
- **Reranker**: BAAI/bge-reranker-v2-m3
- **API Port**: 8900
- **Systemd Service**: `constitutional-ai-backend`
- **CRAG**: Enabled (self-reflection + grading active)

## För AI-modeller som ska arbeta med projektet

1. **Läs först**: `docs/system-overview.md` och `docs/BACKEND_STATUS.md`
2. **För API-ändringar**: Se `docs/guardrails.md` → Route Discovery
3. **För modelländringar**: Se `docs/MODEL_OPTIMIZATION.md`
4. **För kodstil**: Se `CONTRIBUTING.md`

## Vanliga Uppgifter

- **Lägg till endpoint**: Se `docs/guardrails.md` → Route Discovery
- **Ändra modellparametrar**: Se `docs/MODEL_OPTIMIZATION.md`
- **Uppdatera dokumentation**: Uppdatera relevant fil i `docs/`
- **Testa backend**: `curl http://localhost:8900/api/constitutional/health`

## Projektstruktur (High-Level)

```
09_CONSTITUTIONAL-AI/
├── backend/              # FastAPI backend (port 8900)
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── services/     # Business logic (12 services)
│   │   ├── core/         # Exceptions, error handlers
│   │   └── main.py        # FastAPI entry point
│   └── requirements.txt
├── apps/
│   ├── constitutional-gpt/      # Main RAG interface
│   └── constitutional-dashboard/ # Metrics dashboard
├── docs/                 # Dokumentation
│   ├── system-overview.md
│   ├── BACKEND_STATUS.md
│   ├── guardrails.md
│   └── MODEL_OPTIMIZATION.md
├── scrapers/            # Web scrapers (~100 files)
├── indexers/            # ChromaDB indexing scripts
└── AI-INDEX.md          # Denna fil
```

## Services & Ports

| Service | Port | Status | Purpose |
|--------|------|--------|---------|
| Constitutional AI Backend | 8900 | 🟢 Active | FastAPI RAG API |
| llama-server | 8080 | 🟢 Running | Local LLM inference (Mistral-Nemo) |
| Ollama (fallback) | 11434 | Optional | Fallback LLM inference |

## API Endpoints (Key)

- `GET /api/constitutional/health` - Health check
- `POST /api/constitutional/agent/query` - RAG query
- `GET /api/constitutional/stats/overview` - Statistics
- `GET /api/constitutional/collections` - List collections

## Teknisk Stack

- **Backend**: FastAPI (Python 3.14)
- **Frontend**: React + TypeScript + Vite / Next.js 16
- **Vector DB**: ChromaDB (1.37M+ dokument: 538K legal/gov + 829K DiVA research, exkluderas från git)
- **LLM**: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf via llama-server (port 8080), gpt-sw3 (fallback)
- **Embeddings**: BAAI/bge-m3 (1024 dimensions)
- **Reranker**: BAAI/bge-reranker-v2-m3

## Viktiga Noteringar

- **Data exkluderas**: `chromadb_data/`, `pdf_cache/`, `backups/` är stora (16GB+) och exkluderas från git
- **Secrets**: Använd environment variables, aldrig hardcode API keys
- **Systemd**: Backend körs som `constitutional-ai-backend` service
- **Dokumentation**: Alla viktiga filer finns i `docs/` mappen
