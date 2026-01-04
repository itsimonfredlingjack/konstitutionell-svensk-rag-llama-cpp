# GitHub Publication Guide - AI-Läsbar Struktur

## Översikt

Denna guide beskriver hur man strukturerar projektet för GitHub-publicering med fokus på att göra det lättförståeligt för AI-modeller (Claude, ChatGPT, etc.).

## Strategi: Vad ska inkluderas?

### ✅ INKLUDERA (Kod & Dokumentation)

**1. Alla källfiler**
- `backend/` - Hela backend-strukturen
- `apps/` - Alla frontend-applikationer
- `scrapers/` - Scraper-kod
- `indexers/` - Indexeringsskript
- `scripts/` - Utility-skript
- `juridik-ai/` - Juridik AI pipelines

**2. Konfigurationsfiler**
- `requirements.txt`, `pyproject.toml` - Python dependencies
- `package.json` (i varje app) - Node dependencies
- `systemd/` - Service-filer (anonymiserade)
- `.gitignore` - Exkluderingsregler

**3. Dokumentation (KRITISKT för AI-förståelse)**
- `docs/` - All dokumentation
- `README.md` - Huvud-README (skapa om den saknas)
- `CONTRIBUTING.md` - Bidragsguide
- `docs/system-overview.md` - Systemöversikt
- `docs/guardrails.md` - Agent guardrails
- `docs/MODEL_OPTIMIZATION.md` - Modelloptimering
- `docs/BACKEND_STATUS.md` - Backend status

**4. Projektstruktur-filer**
- `forstudie/JURIDIK HOLY SHIT.txt` - Projektvision
- `TESTING_INDEX.md` - Testöversikt
- `TEST_COVERAGE_ANALYSIS.md` - Test coverage

### ❌ EXKLUDERA (Stor data & Secrets)

**1. Stora datamängder (redan i .gitignore)**
- `chromadb_data/` - 16GB ChromaDB data
- `pdf_cache/` - 21GB PDF cache
- `backups/` - 7.5GB backups
- `scraped_data/` - Scraped raw data
- `harvest_results/` - Harvest resultat

**2. Secrets & Environment**
- `.env` - Environment variables
- `.env.local` - Lokala secrets
- API keys i kod (använd environment variables)

**3. Build artifacts**
- `node_modules/` - Node dependencies
- `venv/`, `venv_scraper/` - Python virtual environments
- `dist/`, `build/` - Build outputs
- `__pycache__/` - Python cache

**4. Temporära filer**
- `*.log` - Loggfiler
- `*.tmp` - Temporära filer
- `.cache/` - Cache directories

**5. Känslig data**
- `n8n_workflows/` - Kan innehålla API keys (valfritt)
- `archive/` - Gamla filer (valfritt)

## AI-Läsbar Struktur

### 1. Skapa en omfattande README.md

```markdown
# Constitutional AI

> RAG-system för svenska myndighetsdokument med 521K+ dokument

## Quick Start

1. **Backend**: `cd backend && pip install -r requirements.txt`
2. **Frontend**: `cd apps/constitutional-gpt && npm install`
3. **Start**: `systemctl --user start constitutional-ai-backend`

## Projektstruktur

```
09_CONSTITUTIONAL-AI/
├── backend/              # FastAPI backend (port 8000)
│   ├── app/
│   │   ├── api/          # API routes
│   │   ├── services/     # Business logic
│   │   └── main.py       # FastAPI app
│   └── requirements.txt
├── apps/
│   ├── constitutional-gpt/      # Main RAG interface
│   └── constitutional-dashboard/ # Metrics dashboard
├── docs/                 # Dokumentation
│   ├── system-overview.md
│   ├── guardrails.md
│   └── MODEL_OPTIMIZATION.md
└── scrapers/            # Web scrapers
```

## Dokumentation

- **Systemöversikt**: [docs/system-overview.md](docs/system-overview.md)
- **Backend Status**: [docs/BACKEND_STATUS.md](docs/BACKEND_STATUS.md)
- **API Dokumentation**: [apps/constitutional-dashboard/CONSTITUTIONAL_API.md](apps/constitutional-dashboard/CONSTITUTIONAL_API.md)
- **Modelloptimering**: [docs/MODEL_OPTIMIZATION.md](docs/MODEL_OPTIMIZATION.md)

## Teknisk Stack

- **Backend**: FastAPI (Python 3.14)
- **Frontend**: React + TypeScript + Vite
- **Vector DB**: ChromaDB (521K+ dokument)
- **LLM**: Ollama (ministral-3:14b, gpt-sw3:6.7b)
- **Embeddings**: KBLab Swedish BERT

## Services

| Tjänst | Port | Status |
|--------|------|--------|
| Constitutional AI Backend | 8000 | 🟢 Active |
| Ollama | 11434 | Running |

## API Endpoints

- `GET /api/constitutional/health` - Health check
- `POST /api/constitutional/agent/query` - RAG query
- `GET /api/constitutional/stats/overview` - Statistics

## Development

Se [CONTRIBUTING.md](CONTRIBUTING.md) för kodstil och bidragsguide.
```

### 2. Skapa en AI-INDEX.md

Skapa en fil som AI-modeller kan läsa först för att förstå projektet:

```markdown
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

- **ChromaDB Path**: `/home/ai-server/.../chromadb_data/` (exkluderas från git)
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
```

### 3. Uppdatera .gitignore

Kontrollera att `.gitignore` exkluderar allt som inte ska vara med:

```gitignore
# Stora datamängder (16GB+)
chromadb_data/
pdf_cache/
backups/
scraped_data/
harvest_results/

# Secrets
.env
.env.local
*.key
*.pem

# Build artifacts
node_modules/
venv/
__pycache__/
dist/
build/

# Temporära filer
*.log
*.tmp
.cache/

# Känslig data (valfritt)
n8n_workflows/
archive/
```

## Steg-för-steg: Publicering

### 1. Förberedelse

```bash
# Kontrollera .gitignore
cat .gitignore

# Kontrollera storlek på exkluderade mappar
du -sh chromadb_data/ pdf_cache/ backups/

# Kontrollera att inga secrets är committade
git grep -i "api_key\|secret\|password\|token" -- "*.py" "*.ts" "*.tsx"
```

### 2. Skapa README.md (om den saknas)

```bash
# Skapa en omfattande README
# Se exempel ovan
```

### 3. Skapa AI-INDEX.md

```bash
# Skapa AI-INDEX.md i root
# Se exempel ovan
```

### 4. Verifiera exkluderingar

```bash
# Testa git status (ska inte visa exkluderade filer)
git status

# Kontrollera att stora mappar inte är tracked
git ls-files | grep -E "chromadb_data|pdf_cache|backups"
```

### 5. Commit & Push

```bash
# Stage alla filer
git add .

# Commit med beskrivande meddelande
git commit -m "feat: Add Constitutional AI backend and documentation

- Migrated backend from 02_SIMONS-AI-BACKEND to 09_CONSTITUTIONAL-AI/backend
- Added comprehensive documentation for AI models
- Updated all service references to constitutional-ai-backend
- Added AI-INDEX.md for AI model understanding"

# Push till GitHub
git push origin main
```

## Dokumentationsprioritering för AI

### Nivå 1: Måste ha (för AI-förståelse)
1. `README.md` - Projektöversikt
2. `AI-INDEX.md` - AI-specifik index
3. `docs/system-overview.md` - Arkitektur
4. `docs/BACKEND_STATUS.md` - Service status
5. `docs/guardrails.md` - Agent regler

### Nivå 2: Bör ha (för utveckling)
6. `CONTRIBUTING.md` - Kodstil
7. `docs/MODEL_OPTIMIZATION.md` - Modelloptimering
8. `apps/constitutional-dashboard/CONSTITUTIONAL_API.md` - API docs

### Nivå 3: Bra att ha (för detaljer)
9. `docs/QUICK_START.md` - Quick start
10. `TESTING_INDEX.md` - Testöversikt
11. `docs/eval/README.md` - Evaluation

## Tips för AI-läsbarhet

### 1. Använd tydliga filnamn
- ✅ `system-overview.md` (tydligt)
- ❌ `overview.md` (vagt)

### 2. Inkludera kontext i filer
- Börja varje dokumentationsfil med "Vad är detta?"
- Inkludera länkar till relaterade filer
- Använd tydliga rubriker

### 3. Dokumentera arkitektur
- Diagram över data flow
- Service dependencies
- API endpoint översikt

### 4. Inkludera exempel
- Code examples i dokumentation
- API request/response exempel
- Konfigurationsexempel

### 5. Uppdatera dokumentation
- Håll dokumentation synkad med kod
- Uppdatera när strukturen ändras
- Tagga versioner om möjligt

## Checklista före push

- [ ] `.gitignore` exkluderar stora datamängder
- [ ] Inga secrets i kod eller config
- [ ] `README.md` finns och är komplett
- [ ] `AI-INDEX.md` finns (för AI-förståelse)
- [ ] Alla dokumentationsfiler är uppdaterade
- [ ] Projektstruktur är tydlig
- [ ] API endpoints är dokumenterade
- [ ] System commands är korrekta
- [ ] Inga absoluta paths i dokumentation (använd relativa)
- [ ] Git history är ren (inga secrets i historik)

## Efter push: Verifiera

1. **Kontrollera GitHub**
   - Alla filer syns korrekt
   - Inga stora filer (>100MB)
   - Dokumentation är läsbar

2. **Testa AI-förståelse**
   - Ladda upp repo till Claude/ChatGPT
   - Fråga: "Vad gör detta projekt?"
   - Verifiera att AI förstår strukturen

3. **Uppdatera vid behov**
   - Lägg till mer dokumentation om AI missförstår
   - Uppdatera `AI-INDEX.md` baserat på feedback

## Exempel: Vad AI-modeller behöver veta

När en AI-modell öppnar projektet bör den kunna:

1. **Förstå syftet**: "Detta är ett RAG-system för svenska myndighetsdokument"
2. **Hitta entry points**: "Backend är i `backend/app/main.py`"
3. **Förstå arkitekturen**: "Se `docs/system-overview.md`"
4. **Veta hur man ändrar**: "Se `docs/guardrails.md` för regler"
5. **Förstå API**: "Se `apps/constitutional-dashboard/CONSTITUTIONAL_API.md`"

## Ytterligare resurser

- [GitHub's guide to .gitignore](https://docs.github.com/en/get-started/getting-started-with-git/ignoring-files)
- [Writing great READMEs](https://www.makeareadme.com/)
- [Documentation best practices](https://www.writethedocs.org/guide/)
