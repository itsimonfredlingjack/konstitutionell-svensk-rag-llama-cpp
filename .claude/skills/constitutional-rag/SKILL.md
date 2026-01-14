---
name: constitutional-rag
description: Swedish RAG: llama-server health, ChromaDB search, CRAG pipeline, ports 8080/8900/3001
---

# Constitutional RAG System

## Quick Health Check
```bash
curl -s http://localhost:8900/api/constitutional/health | jq .
curl -s http://localhost:8080/v1/models
lsof -i :3001
```

## Key Files
- `backend/app/services/config_service.py` - All settings
- `backend/app/services/orchestrator_service.py` - RAG pipeline
- `backend/app/services/retrieval_service.py` - ChromaDB search
- `start_system.sh` - llama-server config

## Common Fixes
| Issue | Solution |
|-------|----------|
| Dimension mismatch | Use `_bge_m3_1024` collection suffix |
| Slow inference | Restart llama-server, check `nvidia-smi` |
| CORS error | Add port to `backend/app/config.py` cors_origins |
| No results | Lower `RAG_SIMILARITY_THRESHOLD` (default 0.5) |

## Test Query
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "vad säger lagen om...", "mode": "auto"}'
```
