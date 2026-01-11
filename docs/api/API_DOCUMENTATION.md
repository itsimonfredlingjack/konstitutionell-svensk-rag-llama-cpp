# Constitutional AI Backend API Documentation

**Version:** 2.0.0  
**Base URL:** `http://localhost:8900`  
**Interactive Docs:** `/docs` (Swagger UI) | `/redoc` (ReDoc)

## Quick Start

```bash
# Health check
curl http://localhost:8900/api/constitutional/health

# Query
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Vad är regeringens klimatpolitik?", "mode": "evidence"}'
```

## Endpoints

### Health Check
**GET** `/api/constitutional/health`

Returns service health status.

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "orchestrator": "online",
    "retrieval": "online",
    "llm": "online"
  },
  "timestamp": "2026-01-11T02:00:00.000Z"
}
```

### Agent Query
**POST** `/api/constitutional/agent/query`

Execute RAG query with question answering.

**Headers:**
- `X-Retrieval-Strategy` (optional): `parallel_v1`, `rewrite_v1`, `rag_fusion`, `adaptive`

**Request:**
```json
{
  "question": "Vad är regeringens klimatpolitik?",
  "mode": "evidence",
  "history": []
}
```

**Response:**
```json
{
  "answer": "Regeringen har fattat flera beslut...",
  "sources": [...],
  "mode": "evidence",
  "saknas_underlag": false,
  "evidence_level": "HIGH"
}
```

### Streaming Query
**POST** `/api/constitutional/agent/query/stream`

Server-Sent Events (SSE) streaming response.

**Events:**
- `metadata`: Initial metadata
- `token`: Streaming tokens
- `done`: Completion
- `error`: Error event

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input |
| `SECURITY_VIOLATION` | 403 | Security check failed |
| `LLM_CONNECTION_ERROR` | 503 | LLM service unavailable |
| `LLM_TIMEOUT` | 504 | LLM timeout |

## Code Examples

### JavaScript
```javascript
const response = await fetch('http://localhost:8900/api/constitutional/agent/query', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    question: 'Vad är regeringens klimatpolitik?',
    mode: 'evidence'
  })
});
const data = await response.json();
```

### Python
```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        'http://localhost:8900/api/constitutional/agent/query',
        json={'question': 'Vad är regeringens klimatpolitik?', 'mode': 'evidence'}
    )
    data = response.json()
```

### cURL
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Vad är regeringens klimatpolitik?", "mode": "evidence"}'
```

## Full Documentation

See `/docs` for interactive Swagger UI documentation.
