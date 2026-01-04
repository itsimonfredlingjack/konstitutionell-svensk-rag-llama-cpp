# Constitutional AI - AI Index

> Denna fil är designad för AI-modeller att förstå projektstrukturen snabbt.

## Projektets Syfte

Constitutional AI är ett RAG-system (Retrieval-Augmented Generation) för svenska myndighetsdokument med:
- 521K+ dokument från Riksdagen och svenska myndigheter
- ChromaDB som vector database
- Ollama för lokal LLM-inferens
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
- `app/services/llm_service.py` - Ollama integration

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
Retrieval Service → ChromaDB (521K docs)
    ↓
LLM Service → Ollama (ministral-3:14b)
    ↓
Response → Frontend → User
```

## Viktiga Konfigurationer

- **ChromaDB Path**: Konfigureras i `backend/app/config.py` (data exkluderas från git)
- **Ollama Models**: `ministral-3:14b` (primary), `gpt-sw3:6.7b` (fallback)
- **Embedding Model**: KBLab Swedish BERT (768 dimensions)
- **API Port**: 8000
- **Systemd Service**: `constitutional-ai-backend`

## För AI-modeller som ska arbeta med projektet

1. **Läs först**: `docs/system-overview.md` och `docs/BACKEND_STATUS.md`
2. **För API-ändringar**: Se `docs/guardrails.md` → Route Discovery
3. **För modelländringar**: Se `docs/MODEL_OPTIMIZATION.md`
4. **För kodstil**: Se `CONTRIBUTING.md`

## Vanliga Uppgifter

- **Lägg till endpoint**: Se `docs/guardrails.md` → Route Discovery
- **Ändra modellparametrar**: Se `docs/MODEL_OPTIMIZATION.md`
- **Uppdatera dokumentation**: Uppdatera relevant fil i `docs/`
- **Testa backend**: `curl http://localhost:8000/api/constitutional/health`

## Projektstruktur (High-Level)

```
09_CONSTITUTIONAL-AI/
├── backend/              # FastAPI backend (port 8000)
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
| Constitutional AI Backend | 8000 | 🟢 Active | FastAPI RAG API |
| Ollama | 11434 | Running | Local LLM inference |

## API Endpoints (Key)

- `GET /api/constitutional/health` - Health check
- `POST /api/constitutional/agent/query` - RAG query
- `GET /api/constitutional/stats/overview` - Statistics
- `GET /api/constitutional/collections` - List collections

## Teknisk Stack

- **Backend**: FastAPI (Python 3.14)
- **Frontend**: React + TypeScript + Vite / Next.js 16
- **Vector DB**: ChromaDB (521K+ dokument, exkluderas från git)
- **LLM**: Ollama (ministral-3:14b, gpt-sw3:6.7b)
- **Embeddings**: KBLab Swedish BERT (768 dimensions)

## Viktiga Noteringar

- **Data exkluderas**: `chromadb_data/`, `pdf_cache/`, `backups/` är stora (16GB+) och exkluderas från git
- **Secrets**: Använd environment variables, aldrig hardcode API keys
- **Systemd**: Backend körs som `constitutional-ai-backend` service
- **Dokumentation**: Alla viktiga filer finns i `docs/` mappen
