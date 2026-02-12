# Deployment Guide — Constitutional AI

Production deployment guide for the Swedish government document RAG system.

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32 GB |
| GPU | 8 GB VRAM (RTX 3060) | 12+ GB VRAM (RTX 4070+) |
| Storage | 50 GB | 100 GB (for 521K+ docs) |
| Python | 3.12+ | 3.12 |
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 |

## Quick Start (Docker)

```bash
cd 09_CONSTITUTIONAL-AI

# 1. Configure
cp backend/.env.example backend/.env
# Edit backend/.env — set CONST_CHROMADB_PATH, CONST_API_KEY, etc.

# 2. Download GGUF model (first time only)
# Place the model file in the llama_models Docker volume:
mkdir -p llama_models
wget -O llama_models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf \
    https://huggingface.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF/resolve/main/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf

# 3. Start services
docker compose up -d

# 4. Verify
curl http://localhost:8080/health          # llama-server healthy
curl http://localhost:8900/api/constitutional/health
curl http://localhost:8900/api/constitutional/ready
```

## Manual Installation (without Docker)

### 1. ChromaDB

ChromaDB runs as an embedded database (no separate server needed). Data is stored at the path configured by `CONST_CHROMADB_PATH`.

```bash
# ChromaDB is included in Python dependencies
# Just ensure the data directory exists:
mkdir -p /path/to/chromadb_data
```

### 2. LLM Server

Option A: **llama.cpp (llama-server)** — primary, used in production
```bash
# Build llama.cpp with CUDA support
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make -j$(nproc) LLAMA_CUDA=1

# Download model
wget -O /path/to/models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf \
    https://huggingface.co/bartowski/Mistral-Nemo-Instruct-2407-GGUF/resolve/main/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf

# Start server (OpenAI-compatible API on port 8080)
./llama-server \
    -m /path/to/models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf \
    --host 0.0.0.0 --port 8080 \
    -c 32768 -ngl 99
```

Option B: **Ollama** (optional fallback — not used in production)
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral-nemo
# Runs on http://localhost:11434
# To use: set CONST_LLM_BASE_URL=http://localhost:11434/v1
```

### 3. Backend

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — see "Environment Variables" section below

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### 4. Verify Installation

```bash
# Health check (basic)
curl http://localhost:8900/api/constitutional/health

# Readiness check (deep — verifies ChromaDB, LLM, embeddings)
curl http://localhost:8900/api/constitutional/ready

# Test query
curl -X POST http://localhost:8900/api/constitutional/agent/query \
    -H "Content-Type: application/json" \
    -d '{"question": "Vad är personuppgiftslagen?"}'
```

## Environment Variables

All backend variables use the `CONST_` prefix. See `backend/.env.example` for the full list.

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `CONST_CHROMADB_PATH` | Path to ChromaDB data | `/data/chromadb` |
| `CONST_LLM_BASE_URL` | LLM API endpoint (OpenAI-compatible) | `http://localhost:8080/v1` |

### Recommended

| Variable | Default | Description |
|----------|---------|-------------|
| `CONST_API_KEY` | _(none)_ | API key for write operations. **Set in production\!** |
| `CONST_PORT` | `8900` | Backend listen port |
| `CONST_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CONST_LOG_JSON` | `false` | JSON-formatted log output |
| `CONST_CRAG_ENABLED` | `false` | Enable Corrective RAG pipeline |
| `CONST_RERANKING_ENABLED` | `true` | Jina reranker for search quality |
| `CONST_STRUCTURED_OUTPUT_ENABLED` | `true` | JSON-structured LLM responses |
| `CONST_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v3` | Embedding model (1024 dim) |

### CORS

Origins are configured as a JSON list:
```bash
CONST_CORS_ORIGINS=["http://localhost:5173","http://your-frontend:3000"]
```

## API Documentation

- **Swagger UI**: `http://localhost:8900/docs`
- **ReDoc**: `http://localhost:8900/redoc`

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/constitutional/health` | GET | Basic health check |
| `/api/constitutional/ready` | GET | Deep readiness check |
| `/api/constitutional/agent/query` | POST | RAG query (30 req/min limit) |
| `/api/constitutional/agent/query/stream` | POST | SSE streaming RAG (20 req/min) |
| `/api/constitutional/stats/overview` | GET | Document statistics |
| `/api/constitutional/collections` | GET | ChromaDB collections |
| `/api/constitutional/metrics` | GET | RAG pipeline metrics |

### Rate Limits

- **Query endpoints**: 30 requests/minute per IP
- **Streaming endpoints**: 20 requests/minute per IP
- Returns HTTP 429 when exceeded with `retry_after` header

### Authentication

Write operations (document CRUD) require `X-API-Key` header when `CONST_API_KEY` is set:
```bash
curl -X POST http://localhost:8900/api/documents/ \
    -H "X-API-Key: your-secret-key" \
    -H "Content-Type: application/json" \
    -d '{"content": "...", "collection": "legal_documents"}'
```

## Monitoring

### Health Checks

```bash
# Quick: is the server running?
GET /api/constitutional/health

# Deep: are all dependencies (ChromaDB, LLM, embeddings) available?
GET /api/constitutional/ready
```

### Logs

With `CONST_LOG_JSON=true`, logs are structured JSON for easy parsing:
```json
{"timestamp": "2026-02-07 10:30:00", "level": "INFO", "module": "orchestrator", "message": "Query processed", "request_id": "abc-123"}
```

### Prometheus Metrics

```bash
GET /api/constitutional/metrics/prometheus
```

## Troubleshooting

### ChromaDB connection fails
- Verify `CONST_CHROMADB_PATH` points to a valid directory
- Ensure the directory has correct permissions
- Check if another process is holding a lock on the SQLite DB

### LLM timeouts
- Verify llama-server is running: `curl http://localhost:8080/health`
- Check model availability: `curl http://localhost:8080/v1/models`
- Increase timeout: `CONST_LLM_TIMEOUT=120`
- Check GPU memory — the model may not be fully loaded

### Embedding model fails to load
- First load downloads ~2.3 GB for Jina v3
- Ensure sufficient disk space and internet access
- Model cache: `~/.cache/huggingface/`

### Rate limit exceeded
- Default: 30 req/min for queries, 20 for streaming
- Wait for the `retry_after` period indicated in the 429 response

### Out of GPU memory
- Reduce context window: `-c 16384` in llama-server command
- Use a smaller model quantization (Q4_K_M instead of Q5_K_M)
- Reduce GPU layers: `-ngl 40` instead of `-ngl 99`
- Disable reranking: `CONST_RERANKING_ENABLED=false`
