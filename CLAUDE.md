# CLAUDE.md

Instruktioner för Claude Code i detta repository.

## Projektöversikt

Constitutional AI är ett RAG-system för svenska myndighetsdokument (1.37M+ dokument: 538K juridiska/myndighets + 829K DiVA-forskning). ChromaDB med Jina Embeddings v3 (1024 dim, asymmetrisk encoding) för semantisk sökning, llama-server (llama.cpp) för lokal LLM-inferens, FastAPI backend på port 8900, React+Vite+Three.js frontend på port 3001.

Fristående git-repo i `AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/`.

## Kommandon

### Backend (port 8900)

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Tester
pytest tests/ -v
pytest tests/test_constitution.py -v
pytest tests/test_constitution.py::test_name
pytest -m unit
pytest -m "not slow"

# Opt-in tester
RUN_INTEGRATION_TESTS=1 pytest -m integration
RUN_OLLAMA_TESTS=1 pytest -m ollama

# Lint & format
ruff check .
ruff check --fix .
ruff format .
```

### Frontend (port 3001)

Enda frontend: `apps/constitutional-retardedantigravity/`. Skapa aldrig nya frontend-appar.

```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev       # dev server :3001
npm run build     # tsc -b && vite build
npm run lint      # eslint
```

Frontend ansluter till `VITE_BACKEND_URL` (default `http://localhost:8900`).

### Systemd services

```bash
systemctl --user status constitutional-ai-backend
systemctl --user status constitutional-ai-llm
systemctl --user status constitutional-ai-frontend
journalctl --user -u constitutional-ai-backend -f
```

Starta aldrig om services utan explicit tillåtelse. Kolla alltid `lsof -i :PORT` först.

### Health check

```bash
curl http://localhost:8900/api/constitutional/health | jq .

curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Vad säger GDPR om personuppgifter?","mode":"assist"}' | jq .
```

API-docs: `http://localhost:8900/docs` (Swagger) och `/redoc`.

## Arkitektur

**RAG-stack och modellval:** För beslut om modeller, retrieval-arkitektur och migrationsrekommendationer, använd **`docs/deep-research-by-claude.md`** och **`docs/deep-research-by-chatgpt.md`** som kanoniska källor. Se även `docs/README_DOCS_AND_RAG_INSTRUCTIONS.md` för vilka dokument som är aktuella vs arkiverade.

### RAG-pipeline

```
User Query → Frontend → POST /api/constitutional/agent/query/stream
  → OrchestratorService (~950 rader, central koordinator)
    → IntentClassifier (klassificerar frågetyp)
    → QueryRewriter (omskrivning/expansion)
    → RetrievalOrchestrator (Fas 1-4, adaptiv eskalering)
      → RetrievalService → ChromaDB (1.37M+ docs)
      → BM25Service (sparse keyword search)
      → RAGFusion (multi-query + RRF-merge)
    → RerankingService (Jina cross-encoder)
    → GraderService (Qwen 0.5B, binär relevansgradering)
    → LLMService → llama-server (Ministral-3-14B-Instruct-2512)
    → GuardrailService (Jail Warden v2, blockerar hallucinationer i EVIDENCE)
    → CriticService (Critic-Revise loop)
  → SSE streaming → Frontend
```

Tre frågelägen:
- **EVIDENCE** (temp 0.15): Strikt källbaserat
- **ASSIST** (temp 0.4): Guidat med källor som kontext
- **CHAT** (temp 0.7): Konversationellt

### Services (`backend/app/services/`, 30 moduler)

| Service | Ansvar |
|---------|--------|
| `orchestrator_service.py` | Central pipeline-koordinator |
| `retrieval_orchestrator.py` | Fas 1-4 retrieval med adaptiv eskalering |
| `retrieval_service.py` | ChromaDB vektorsökning |
| `llm_service.py` | llama-server integration med streaming |
| `embedding_service.py` | Jina v3 embeddings (asymmetrisk) |
| `reranking_service.py` | Jina cross-encoder reranking |
| `grader_service.py` | Dokumentrelevans (Qwen 0.5B) |
| `graph_service.py` | LangGraph state machine för CRAG |
| `guardrail_service.py` | Hallucinationsdetektion |
| `intent_classifier.py` | Frågetypklassificering |
| `intent_routing.py` | Intent→collection-mappning |
| `query_rewriter.py` | Query-expansion |
| `bm25_service.py` | Sparse keyword-sökning |
| `rag_fusion.py` | Multi-query fusion med RRF |
| `source_hierarchy.py` | Källprioritering (SFS > prop/SOU) |
| `prompt_service.py` | Systemprompt-konstruktion |
| `streaming_service.py` | SSE-streaming |
| `sse_stream_service.py` | SSE stream-hantering |
| `generation_service.py` | LLM-output generering |
| `critic_service.py` | Critic-Revise loop |
| `agentic_service.py` | Agentiskt flöde |
| `confidence_signals.py` | Adaptiva confidence-signaler |
| `structured_output_service.py` | JSON-output parsning |
| `config_service.py` | Konfigurationshantering |
| `crag_service.py` | CRAG-logik |
| `legal_abbreviations.py` | Svenska juridiska termer |
| `swedish_compound_splitter.py` | Sammansatt-ordsdelning |
| `query_processor_service.py` | Frågebearbetning |
| `rag_models.py` | Datamodeller |
| `base_service.py` | Bas-klass för services |

Services är singletons via `get_*_service()` factory-funktioner.

### Frontend (`apps/constitutional-retardedantigravity/`)

React 19 + Vite 7 + TypeScript 5.9 + Three.js (React Three Fiber/Drei) + Tailwind CSS 4 + Zustand 5.

- `src/App.tsx` — Root med 3D canvas-bakgrund
- `src/stores/useAppStore.ts` — Zustand store: query state, SSE-streaming, pipeline-visualisering
- `src/components/3d/` — Three.js 3D-komponenter (Substrate, SourceViewer3D, ConnectorLogic)
- `src/components/ui/` — UI-komponenter (TrustHull, HeroSection, ChatView, QueryBar, SourcesPanel, PipelineVisualizer, AnswerWithCitations, ConfidenceBadge m.fl.)

31 komponenter totalt.

### API routes

Alla prefixade med `/api/constitutional` (definierade i `backend/app/api/constitutional_routes.py`):

- `GET /health` — Hälsokontroll
- `GET /ready` — Djup readiness-check
- `GET /stats/overview` — Collection-statistik
- `GET /collections` — Lista ChromaDB-collections
- `GET /metrics` — Pipeline-metrics
- `GET /metrics/prometheus` — Prometheus-format
- `POST /agent/query` — RAG-fråga (JSON)
- `POST /agent/query/stream` — RAG-fråga (SSE-streaming, används av frontend)
- `POST /search` — Dokumentsökning
- `WS /ws/harvest` — Live harvest-progress

### Konfiguration

Backend-inställningar i `backend/app/config.py` via pydantic-settings. Miljövariabler prefixade med `CONST_`. Laddar `.env` automatiskt.

Viktiga variabler: `CONST_CRAG_ENABLED`, `CONST_CRAG_ENABLE_SELF_REFLECTION`, `CONST_LLM_BASE_URL`, `CONST_DEBUG`, `CONST_LOG_LEVEL`.

## Kodstil

### Python

Ruff: line-length 100, target py310. Konfigurerat i `pyproject.toml`. Type hints obligatoriskt. Import-ordning: stdlib → tredjepartsbibliotek → lokala. Pytest: `asyncio_mode = "auto"`.

### TypeScript/React

Funktionella komponenter. `import type` för type-only imports. Tailwind CSS med `clsx`/`tailwind-merge`. Zustand för state.

### Commits

Conventional commits: `feat(scope): description`, `fix(scope): description`, etc.

## Data

- **ChromaDB**: `chromadb_data/` (~37GB, exkluderat från git)
- **Collections** (alla suffixade `_jina_v3_1024`): `swedish_gov_docs` (304K), `riksdag_documents_p1` (230K), `sfs_lagtext`, `procedural_guides`, DiVA-collections (829K)
- **Totalt**: 1.37M+ dokument (538K juridiska/myndighets + 829K DiVA-forskning)
- **Embeddings**: jinaai/jina-embeddings-v3 (1024 dim, CC-BY-NC-4.0)
- **Reranker**: jinaai/jina-reranker-v2-base-multilingual
- **LLM**: Ministral-3-14B-Instruct-2512-Q4_K_M.gguf via llama-server port 8080
- **Grading-modell**: Qwen2.5-0.5B-Instruct-Q8_0.gguf
- **Fallback-modell**: Ministral-3-14B (samma som primary, ingen separat fallback)
- **CRAG**: Aktiverat i .env (grading + self-reflection)

## Guardrails

- **Aldrig** modifiera `constitutional_routes.py`, systemd-filer eller modellparametrar utan att fråga först
- **Aldrig** använda Playwright/Selenium utan explicit tillåtelse
- **Aldrig** radera ChromaDB-data
- **Alltid** gör route discovery (grep routes, kolla OpenAPI) innan du påstår att en endpoint inte finns
- Modellparameter-ändringar ska dokumenteras i `docs/MODEL_OPTIMIZATION.md`
- Systemprompt-ändringar ska testas med varierade frågor innan deploy
