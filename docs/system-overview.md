# Constitutional AI - System Overview

> Svenska myndighetsdokument - sökning, analys och RAG

**Status:** Production
**Dokument:** 521,798
**Updated:** 2025-12-15

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Total Documents | 521,798 |
| Vector Dimensions | 768 |
| Embedding Model | KBLab Swedish BERT |
| Storage | ChromaDB (migrated from Qdrant) |
| LLM | Mistral-Nemo-Instruct-2407 (GGUF via llama-server) |

---

## Data Sources

### Riksdagen (Parliament)
- **Dokument:** ~230K
- **Typer:** prop, mot, sou, bet, ds
- **API:** data.riksdagen.se
- **Collection:** `riksdag_documents_p1`

### Swedish Government Docs
- **Dokument:** ~305K
- **Typer:** SFS, propositioner, remisser
- **Collection:** `swedish_gov_docs`

### DiVA (Academic)
- **Dokument:** ~960K metadata (ej indexerat)
- **Källa:** DiVA Portal JSON exports

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     constitutional-cli                       │
│         search | status | harvest | embed | ingest          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       RAG API (8900)                         │
│              /search /health /embed                          │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Qdrant    │      │llama-server │      │    n8n      │
│   (6333)    │      │   (8080)    │      │   (5678)    │
│  521K docs  │      │Mistral-Nemo │      │  Workflows  │
└─────────────┘      └─────────────┘      └─────────────┘
```

---

## Services

| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| Constitutional AI Backend | 8000 | 🟢 Active | FastAPI RAG API |
| Qdrant | 6333 | Deprecated | Vector database (migrated to ChromaDB) |
| RAG API | 8900 | On-demand | Search + LLM |
| llama-server | 8080 | Running | Local LLM inference (OpenAI-compatible) |
| Ollama | 11434 | Optional | Legacy fallback |
| n8n | 5678 | Running | Workflow automation |

### Backend Service Status

| Tjänst                    | Status     | Port | Autostart   |
|---------------------------|------------|------|-------------|
| Constitutional AI Backend | 🟢 Active  | 8000 | ✅ Enabled  |
| Simons AI Backend         | 🔴 Removed | -    | ❌ Disabled |

**Bekräftade Ändringar:**
1. ✅ simons-ai-backend.service borttagen från systemd
2. ✅ Port 8000 ägs av constitutional-ai-backend
3. ✅ Health endpoint svarar korrekt
4. ✅ RAG queries fungerar (ministral-3:14b, ~23s)

**System Commands:**
```bash
# Status
systemctl --user status constitutional-ai-backend

# Restart
systemctl --user restart constitutional-ai-backend

# Live logs
journalctl --user -u constitutional-ai-backend -f
```

**API Base URL:** `http://localhost:8000/api/constitutional`

All Constitutional AI-logik är nu fristående i `09_CONSTITUTIONAL-AI/backend/` med egen systemd service! 🚀

---

## Collections (Qdrant)

| Collection | Points | Dimensions | Use Case |
|------------|--------|------------|----------|
| documents | 521,798 | 768 | Main search index |
| obs_chunks | 0 | 768 | Second brain chunks |
| derivatives | 0 | 768 | Generated content |

---

## Key Files

```
09_CONSTITUTIONAL-AI/
├── backend/                   # Backend application (NEW)
│   ├── app/
│   │   ├── main.py            # FastAPI application
│   │   ├── config.py           # Configuration
│   │   ├── api/               # API routes
│   │   ├── services/          # Business logic services
│   │   ├── core/              # Core utilities (exceptions, handlers)
│   │   └── utils/             # Utility functions
│   ├── requirements.txt       # Python dependencies
│   └── pyproject.toml         # Project configuration
├── constitutional_cli.py      # Unified CLI
├── constitutional              # Bash wrapper
├── rag_benchmark.py           # Quality testing
├── chromadb_to_qdrant.py      # Migration tool
├── corpus_bridge.py           # Corpus → Second Brain
├── chromadb_data/             # Original ChromaDB (backup)
├── systemd/                   # Systemd service files
│   └── constitutional-ai-backend.service
└── docs/                      # Documentation
    ├── constitutional-cli.md
    ├── system-overview.md
    └── migration-log.md
```

---

## Benchmark Results (2025-12-15)

**Grade: A**

| Metric | Value |
|--------|-------|
| Queries | 19/20 successful |
| Mean Score | 0.7302 |
| Keyword Hit Rate | 81% |
| Mean Latency | 113s (with LLM) |

### By Category
- Social: 0.783
- Municipal: 0.773
- Health: 0.748
- Administrative: 0.740
- Education: 0.737

---

## Common Tasks

### Search Documents
```bash
constitutional search "GDPR personuppgifter" --top-k 10
```

### Check System Status
```bash
constitutional status
```

### Run Benchmark
```bash
constitutional benchmark --quick
```

### Ingest New Documents
```bash
constitutional ingest ./nya_dokument/ --recursive
```

---

## Related

- [[constitutional-cli]] - CLI documentation
- [[migration-log]] - ChromaDB → Qdrant migration
- [[rag-benchmark]] - Benchmark methodology
- [[second-brain-architecture]] - Memory engine design
