# Constitutional AI

RAG-system för svenska myndighetsdokument. Semantisk sökning och AI-genererade svar baserade på 1.37M+ dokument från Riksdagen, myndigheter, kommuner och DiVA-forskning. Allt körs lokalt — inga molntjänster.

## Vad ingår

```
backend/          FastAPI RAG-backend med 30 service-moduler (port 8900)
apps/             React-frontend med 3D-visualisering (port 3001)
scrapers/         Web scrapers för 30+ svenska myndigheter + kommun- och mediascrapers
indexers/         ChromaDB-indexeringsskript (25+ scripts)
eval/             Utvärdering (RAGAS, retrieval quality, chunk analysis)
docs/             Dokumentation och arkitektur
```

## Tech Stack

### Backend (Python 3.12)

| Komponent | Teknik |
|-----------|--------|
| API | FastAPI 0.109+, Uvicorn, Pydantic v2 |
| Vector DB | ChromaDB (~37GB, 1.37M+ dokument) |
| Embeddings | jinaai/jina-embeddings-v3 (1024 dim, asymmetrisk encoding) |
| Reranker | jinaai/jina-reranker-v2-base-multilingual (cross-encoder, XLM-RoBERTa, 278M params) |
| LLM | Ministral-3-14B-Instruct-2512 Q4_K_M (8.24GB) via llama-server |
| Grading-modell | Qwen2.5-0.5B-Instruct Q8_0 (dokument-relevansgradering) |
| Pipeline | LangGraph (CRAG med relevance grading + self-reflection) |
| Sparse search | BM25 |
| Fusion | RAG-Fusion med Reciprocal Rank Fusion |
| Hallucinationsskydd | Jail Warden v2 (guardrail service) |
| HTTP-klient | httpx |
| Linting | Ruff (line-length 100, target py310) |
| Tester | pytest, pytest-asyncio |

### Frontend (TypeScript)

| Komponent | Teknik |
|-----------|--------|
| UI | React 19, TypeScript 5.9 |
| Build | Vite 7 |
| 3D | Three.js 0.182 via React Three Fiber 9 + Drei 10 |
| Styling | Tailwind CSS 4 |
| State | Zustand 5 |
| Animation | Framer Motion 12 |
| Ikoner | Lucide React |

### Infrastruktur

| Komponent | Teknik |
|-----------|--------|
| Hosting | Self-hosted, RTX 4070 12GB VRAM |
| LLM-runtime | llama-server (llama.cpp) port 8080 |
| Process | 3 systemd user services (backend, llm, frontend) |
| Containers | Docker Compose (ChromaDB, llama-server, backend) |
| CI/CD | GitHub Actions — ruff, mypy, pytest, eslint, tsc build |

## RAG-pipeline

```
Query → IntentClassifier → QueryRewriter
  → RetrievalOrchestrator (4 faser)
    ├─ Fas 1: Parallell sökning i alla collections
    ├─ Fas 2: Query-dekontextualisering
    ├─ Fas 3: RAG-Fusion (multi-query + RRF-merge)
    └─ Fas 4: Adaptiv retrieval (confidence-baserad eskalering)
  → Reranking (Jina cross-encoder)
  → GraderService (Qwen 0.5B, binär relevansgradering per dokument)
  → LLM (Ministral-3-14B, streamas via SSE)
  → GuardrailService (blockerar hallucinationer i EVIDENCE-läge)
  → CriticService (Critic-Revise loop)
  → Svar till frontend
```

### Backend-services (30 moduler i `backend/app/services/`)

| Service | Ansvar |
|---------|--------|
| `orchestrator_service.py` | Central pipeline-koordinator (~950 rader) |
| `retrieval_orchestrator.py` | Fas 1–4 retrieval med adaptiv eskalering |
| `retrieval_service.py` | ChromaDB vektorsökning |
| `llm_service.py` | llama-server (OpenAI-kompatibelt API) med streaming |
| `embedding_service.py` | Jina v3 embeddingberäkning |
| `reranking_service.py` | Jina cross-encoder reranking |
| `grader_service.py` | Dokumentrelevansgradering (Qwen 0.5B) |
| `graph_service.py` | LangGraph state machine för CRAG |
| `guardrail_service.py` | Hallucinationsdetektion (Jail Warden v2) |
| `intent_classifier.py` | Frågetypklassificering |
| `intent_routing.py` | Intent→collection-mappning |
| `query_rewriter.py` | Query-expansion och reformulering |
| `bm25_service.py` | Sparse keyword-sökning |
| `rag_fusion.py` | Multi-query fusion med RRF |
| `source_hierarchy.py` | Källprioritering (SFS > prop/SOU) |
| `prompt_service.py` | Systemprompt-konstruktion |
| `streaming_service.py` | SSE-streaming |
| `sse_stream_service.py` | SSE stream-hantering |
| `generation_service.py` | LLM-output generering |
| `critic_service.py` | Critic-Revise loop |
| `agentic_service.py` | Agentiskt flöde |
| `confidence_signals.py` | Fas 4 adaptiva confidence-signaler |
| `structured_output_service.py` | JSON-output parsning |
| `config_service.py` | Konfigurationshantering |
| `legal_abbreviations.py` | Svenska juridiska termer och förkortningar |
| `swedish_compound_splitter.py` | Svensk sammansatt-ordsdelning |
| `query_processor_service.py` | Frågebearbetning |
| `crag_service.py` | CRAG-logik |
| `rag_models.py` | Datamodeller för RAG |
| `base_service.py` | Bas-klass för alla services |

### Frågelägen

| Läge | Temperatur | Top_P | Max tokens | Syfte |
|------|-----------|-------|------------|-------|
| EVIDENCE | 0.15 | 0.9 | 1024 | Strikt källbaserat, hög precision |
| ASSIST | 0.4 | 0.9 | 1024 | Guidat svar med källor som kontext |
| CHAT | 0.7 | 0.9 | 512 | Konversationellt, friare |

## Datakällor

### ChromaDB-collections (alla suffixade `_jina_v3_1024`)

| Collection | Dokument | Innehåll |
|------------|----------|----------|
| `swedish_gov_docs` | 304K | Myndighetstexter, SOU |
| `riksdag_documents_p1` | 230K | Motioner, riksdagstryck |
| `sfs_lagtext` | — | Svensk författningssamling |
| `procedural_guides` | — | Handläggningsguider |
| DiVA-collections | 829K | Forskningspublikationer (KTH, LU, SU, UU, Chalmers, LiU m.fl.) |
| **Totalt** | **1.37M+** | |

### Scrapers

**Rot-scrapers (21 filer):** Bolagsverket, Boverket, DO, Elsäkerhetsverket, Energimyndigheten, IMY, Jordbruksverket, Livsmedelsverket, Migrationsverket, MSB, PTS, SCB, SFS (Riksdagen). Plus OCR-processor och SFS-uppdaterare.

**Myndighets-scrapers (`scrapers/myndigheter/`, 40 filer):** Arbetsförmedlingen, ARN, Finansinspektionen, Kronofogden, PRV, Riksbanken, ESV, Folkhälsomyndigheten, Försäkringskassan, JK, Kemikalieinspektionen, Konjunkturinstitutet, Konsumentverket, Naturvårdsverket, Skatteverket, Socialstyrelsen, Spelinspektionen, Statskontoret, Trafikanalys, Trafikverket, Vetenskapsrådet, Skolverket, SMHI, Tillväxtverket.

**Kommun-scrapers (`scrapers/kommuner/`, 4 filer):** Djupskrapning av kommunala dokument.

**Media-scrapers (`scrapers/media/`, 8 filer):** Nyhetsskrapning, sitemap-crawling, batch-insamling.

## Kom igång

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### Frontend

```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev
```

### Eller via Docker Compose

```bash
docker compose up
```

### API-dokumentation

Swagger UI: `http://localhost:8900/docs`

### API-endpoints

| Metod | Route | Syfte |
|-------|-------|-------|
| GET | `/api/constitutional/health` | Hälsokontroll |
| GET | `/api/constitutional/ready` | Djup readiness-check |
| GET | `/api/constitutional/stats/overview` | Statistik över collections |
| GET | `/api/constitutional/collections` | Lista ChromaDB-collections |
| GET | `/api/constitutional/metrics` | Pipeline-metrics |
| GET | `/api/constitutional/metrics/prometheus` | Prometheus-format |
| POST | `/api/constitutional/agent/query` | RAG-fråga (JSON) |
| POST | `/api/constitutional/agent/query/stream` | RAG-fråga (SSE-streaming) |
| POST | `/api/constitutional/search` | Dokumentsökning |
| WS | `/api/constitutional/ws/harvest` | Live harvest-progress |

## Portar

| Tjänst | Port |
|--------|------|
| Frontend (Vite dev) | 3001 |
| Backend (FastAPI) | 8900 |
| llama-server (llama.cpp) | 8080 |
| ChromaDB (Docker) | 8100 |

## Tester

```bash
cd backend
pytest tests/ -v                            # alla unit-tester
pytest -m "not integration and not slow"    # snabbkörning
RUN_INTEGRATION_TESTS=1 pytest -m integration  # integrationstester
RUN_OLLAMA_TESTS=1 pytest -m ollama            # ollama-tester
```

16 testfiler, ~4700 rader.

## Konfiguration

Backend-inställningar i `backend/app/config.py` via pydantic-settings. Alla miljövariabler prefixade med `CONST_`:

| Variabel | Default | Syfte |
|----------|---------|-------|
| `CONST_PORT` | 8900 | Backend-port |
| `CONST_LLM_BASE_URL` | `http://localhost:8080/v1` | llama-server URL |
| `CONST_CRAG_ENABLED` | false | Aktivera CRAG (sätts till true i .env) |
| `CONST_CRAG_ENABLE_SELF_REFLECTION` | false | CRAG self-reflection (sätts till true i .env) |
| `CONST_DEBUG` | false | Debug-läge |
| `CONST_LOG_LEVEL` | INFO | Loggnivå |

## Licens

[TBD]
