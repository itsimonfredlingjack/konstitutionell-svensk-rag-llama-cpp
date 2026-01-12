# 📋 Constitutional AI - Projektstruktur

> **VARNING:** Läs detta innan du gör ändringar!

---

## 🎯 PROJEKTETS SYFTE

**Constitutional AI** är ett svenskt RAG-system (Retrieval-Augmented Generation) för myndighetsdokument.

- **538K+ dokument** i ChromaDB
- **Agentic LangGraph pipeline** med självkorrigering
- **3D React-frontend** med Three.js
- **Llama.cpp-modeller** (lokala, inga moln-tjänster)

---

## 🏗️ KRITISK STRUKTUR (DETTA ÄR PROJEKTET)

```
09_CONSTITUTIONAL-AI/
│
├── 🟢 backend/                          # FASTAPI RAG-SYSTEM (port 8900)
│   ├── app/
│   │   ├── main.py                      # Backend entry point
│   │   ├── api/                         # API routes
│   │   └── services/                    # Business logic
│   └── requirements.txt
│
├── 🟢 apps/
│   └── 🟡 constitutional-retardedantigravity/   # DEN RIKTIGA FRONTENDEN!
│       ├── src/                        # React + TypeScript + Three.js
│       ├── index.css                    # STIL: #E7E5E4 (gråvit bakgrund)
│       └── package.json
│
├── 🟢 chromadb_data/                    # 538K+ SVENSKA DOKUMENT (15GB+)
│   └── [collections]                    # Exkluderad från git
│
├── 🟢 llama.cpp/                        # OFFICIELT LLAMA.CPP REPO
│   ├── build/                           # Byggda modeller
│   ├── models/                          # GGUF-modeller
│   └── scripts/                         # Konverteringsskript
│
├── 🟢 nerve-center/                    # SYSTEM MONITORING (port 3003)
│   ├── api/main.py                      # FastAPI backend
│   ├── src/                             # React frontend
│   └── README.md                        # Övervakar: GPU, Ollama, RAG-pipeline
│
├── 🟢 docs/                             # DOKUMENTATION
│   ├── system-overview.md
│   ├── BACKEND_STATUS.md
│   └── MODEL_OPTIMIZATION.md
│
└── 🟢 scrapers/                         # DOKUMENTHÄMTNING
    ├── myndigheter/                     # Myndighetsscrapers
    ├── kommuner/                        # Kommunsscrapers
    └── media/                           # Mediascrapers
```

---

## 🎨 GRÅVITA HEMSIDAN (FRONTEND)

**Sökväg:** `apps/constitutional-retardedantigravity/`

**Funktioner:**
- **React + Vite + TypeScript**
- **3D Visualisering** med Three.js (Substrate, SourceViewer3D)
- **Streaming** av LLM-svar i realtid
- **Agentic Pipeline Visualization** (Retrieval → Grading → Response)

**Färgschema:**
- Bakgrund: `#E7E5E4` (Stone-200 - varmgrå/beige)
- Accent: `#0f766e` (Teal-700 - cyan-glow)
- Text: `#1c1917` (Stone-900 - mörk)

**Starta:**
```bash
cd apps/constitutional-retardedantigravity
npm run dev
# Port: 3001
```

---

## ⚙️ BACKEND (RAG-SYSTEM)

**Sökväg:** `backend/`

**Teknik:**
- **FastAPI** (Python 3.14)
- **ChromaDB** (Vector DB)
- **Ollama** (LLM runtime)
- **LangGraph** (Agentic pipeline)

**Modeller:**
- Ministral-3:14b
- GPT-sw3:6.7b
- Qwen

**Starta:**
```bash
cd backend
pip install -r requirements.txt
systemctl --user start constitutional-ai-backend
# Port: 8900
```

**API Dokumentation:** `http://localhost:8900/docs`

---

## 🧠 LLM-MODELLER (LLAMA.CPP)

**Sökväg:** `llama.cpp/`

**Innehåll:**
- Officiellt llama.cpp repo
- GGUF-modeller för lokalinferens
- Konverteringsskript från HuggingFace

**Modell-format:** GGUF (Quantized)
- `Qwen2.5-0.5B-Instruct-Q8_0.gguf`
- Flere modeller i `models/`

**Bygga/modifiera modeller:**
```bash
cd llama.cpp
./convert_hf_to_gguf.py [model-path]
```

---

## 📊 NERVE CENTER (SYSTEM MONITORING)

**Sökväg:** `nerve-center/`

**Funktioner:**
- **GPU Monitoring**: NVIDIA metrics (VRAM, temp, utilization)
- **Service Health**: Ollama, systemd, Docker containers
- **Agent Loop Pipeline**: RAG pipeline status
- **Real-time Updates**: WebSocket every 2s

**Starta:**
```bash
cd nerve-center/api
python main.py
# Port: 3003
# Frontend: / (via FastAPI serve)
```

---

## 🗂️ DATA & INDEXING

**Sökvägar:**
- `chromadb_data/` - 538K+ svenska myndighetsdokument (15GB+)
- `scrapers/` - Webb-scrapers för dokument
- `indexers/` - ChromaDB indexing scripts
- `pdf_cache/` - Cache för PDF-dokument

**Collections:**
- `swedish_gov_docs`: 304,871 documents
- `riksdag_documents_p1`: 230,143 documents

---

## 🚫 VAD SOM INTE HÖR HEM HÄR

**Felaktiga mappar som har tagits bort:**
- ❌ `frontend/` (Streamlit - fel typ av frontend)
- ❌ `apps/constitutional-dashboard/` (SOVIS Google Nest Hub dashboard → flyttad till `google-home-hack/`)
- ❌ `apps/constitutional-gpt-database/` (tom mapp)

**Om du ser dessa:** De ska inte finnas. Radera dem om de dyker upp.

---

## 📝 VIKTIGA DOKUMENT

| Fil | Syfte |
|-----|-------|
| `README.md` | Allmän projektöversikt |
| `AGENTS.md` | Instruktioner för AI-agenter |
| `FRONTEND_README.md` | Frontend guardrails (LÄS INNAN ÄNDRINGAR) |
| `.cursorrules` | Kodstandard för AI-agenter |
| `CONTRIBUTING.md` | Bidragsguide |
| `docs/system-overview.md` | Detaljerad systembeskrivning |
| `docs/BACKEND_STATUS.md` | Backend status |
| `docs/MODEL_OPTIMIZATION.md` | Modelloptimering |

---

## 🔧 SNABBSTART

### 1. Backend (RAG-system)
```bash
cd backend
pip install -r requirements.txt
systemctl --user start constitutional-ai-backend
# Kolla: http://localhost:8900/docs
```

### 2. Frontend (Gråvita hemsidan)
```bash
cd apps/constitutional-retardedantigravity
npm run dev
# Öppna: http://localhost:3001
```

### 3. Nerve Center (Monitoring)
```bash
cd nerve-center/api
python main.py
# Öppna: http://localhost:3003
```

### 4. Ollama (LLM runtime)
```bash
ollama list
ollama pull ministral:3-14b
ollama run ministral:3-14b
```

---

## 🌐 PORTAR & SERVICES

| Tjänst | Port | Status |
|--------|------|--------|
| Backend (FastAPI) | 8900 | 🟢 Active |
| Frontend (React) | 3001 | 🟢 Active |
| Nerve Center | 3003 | 🟢 Active |
| Ollama | 11434 | 🟢 Running |

---

## ⚠️ KRITISKA REGLER

1. **ANVÄND BARA DENNA FRONTEND:** `apps/constitutional-retardedantigravity/`
2. **INTE STREAMLIT:** React + Three.js är den enda riktiga frontend
3. **BACKEND PORT:** 8900 (NOT 8000)
4. **DATA ÄR STORT:** `chromadb_data/` är 15GB+ - exkludera från git
5. **INGA HÅRDKODADE IP:** Använd miljövariabler

---

## 🤖 FÖR AI-AGENTER

**INNAN DU GÖR NÅGOT:**
1. 📖 Läs `AGENTS.md`
2. 📖 Läs `.cursorrules`
3. 📖 Läs `FRONTEND_README.md` (OM du ska jobba med frontend)
4. 🔍 Kolla om frontend redan finns (JA: i `apps/constitutional-retardedantigravity/`)

**OM DU FÅR INSTRUKTION ATT SKAPA FRONTEND:**
- ✅ STOPPA
- ✅ Använd den riktiga appen: `apps/constitutional-retardedantigravity/`
- ❌ Skapa INGA nya React-appar
- ❌ Använd INTE Streamlit

---

**Senast uppdaterad:** 2026-01-12
