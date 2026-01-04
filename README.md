# Constitutional AI

> RAG-system för svenska myndighetsdokument med 521K+ dokument

[![Status](https://img.shields.io/badge/status-production-green)]()
[![Backend](https://img.shields.io/badge/backend-FastAPI-blue)]()
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-blue)]()

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
systemctl --user start constitutional-ai-backend
```

### Frontend

```bash
cd apps/constitutional-gpt
npm install
npm run dev
```

## Projektstruktur

```
09_CONSTITUTIONAL-AI/
├── backend/              # FastAPI backend (port 8000)
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── services/     # Business logic (12 services)
│   │   ├── core/         # Exceptions, error handlers
│   │   └── main.py       # FastAPI entry point
│   └── requirements.txt
├── apps/
│   ├── constitutional-gpt/      # Main RAG interface (Next.js 16)
│   └── constitutional-dashboard/ # Metrics dashboard (Vite + React)
├── docs/                 # Dokumentation
│   ├── system-overview.md
│   ├── BACKEND_STATUS.md
│   ├── guardrails.md
│   └── MODEL_OPTIMIZATION.md
├── scrapers/            # Web scrapers (~100 files)
├── indexers/            # ChromaDB indexing scripts
└── AI-INDEX.md          # AI-specifik index (för AI-modeller)
```

## Dokumentation

### För AI-modeller
- **AI-INDEX.md** - Start här för AI-förståelse

### Systemdokumentation
- **Systemöversikt**: [docs/system-overview.md](docs/system-overview.md)
- **Backend Status**: [docs/BACKEND_STATUS.md](docs/BACKEND_STATUS.md)
- **API Dokumentation**: [apps/constitutional-dashboard/CONSTITUTIONAL_API.md](apps/constitutional-dashboard/CONSTITUTIONAL_API.md)
- **Modelloptimering**: [docs/MODEL_OPTIMIZATION.md](docs/MODEL_OPTIMIZATION.md)
- **Agent Guardrails**: [docs/guardrails.md](docs/guardrails.md)

### Utveckling
- **Bidragsguide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **GitHub Publicering**: [docs/GITHUB_PUBLICATION_GUIDE.md](docs/GITHUB_PUBLICATION_GUIDE.md)

## Teknisk Stack

- **Backend**: FastAPI (Python 3.14)
- **Frontend**: React + TypeScript + Vite / Next.js 16
- **Vector DB**: ChromaDB (521K+ dokument)
- **LLM**: Ollama (ministral-3:14b, gpt-sw3:6.7b)
- **Embeddings**: KBLab Swedish BERT (768 dimensions)

## Services

| Tjänst | Port | Status |
|--------|------|--------|
| Constitutional AI Backend | 8000 | 🟢 Active |
| Ollama | 11434 | Running |

## API Endpoints

### Health & Stats
- `GET /api/constitutional/health` - Health check
- `GET /api/constitutional/stats/overview` - Overview statistics
- `GET /api/constitutional/collections` - List collections

### RAG Queries
- `POST /api/constitutional/agent/query` - RAG query (EVIDENCE/ASSIST/CHAT mode)
- `POST /api/constitutional/agent/query/stream` - Streaming RAG query

### Search
- `POST /api/constitutional/search` - Document search

Se [API Dokumentation](apps/constitutional-dashboard/CONSTITUTIONAL_API.md) för fullständig lista.

## Data

- **Total Documents**: 521,798
- **Collections**: 
  - `swedish_gov_docs`: 304,871 documents
  - `riksdag_documents_p1`: 230,143 documents
  - `riksdag_documents`: 10 documents
- **Storage**: ChromaDB (data exkluderas från git)

## Development

### Backend Development

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend Development

```bash
cd apps/constitutional-gpt
npm install
npm run dev
```

### Testing

```bash
# Health check
curl http://localhost:8000/api/constitutional/health | jq .

# RAG query
curl -X POST http://localhost:8000/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Vad säger GDPR om personuppgifter?","mode":"assist"}' | jq .
```

## System Commands

```bash
# Backend service
systemctl --user status constitutional-ai-backend
systemctl --user restart constitutional-ai-backend
journalctl --user -u constitutional-ai-backend -f
```

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

## Viktiga Noteringar

- **Data exkluderas**: `chromadb_data/`, `pdf_cache/`, `backups/` är stora (16GB+) och exkluderas från git
- **Secrets**: Använd environment variables, aldrig hardcode API keys
- **Systemd**: Backend körs som `constitutional-ai-backend` service
- **Dokumentation**: Alla viktiga filer finns i `docs/` mappen

## Contributing

Se [CONTRIBUTING.md](CONTRIBUTING.md) för kodstil och bidragsguide.

## License

[Lägg till license här]

## Kontakt

[Lägg till kontaktinfo här]
