# Constitutional AI Dashboard API Endpoints

Backend API for the Constitutional AI Dashboard. Provides access to ChromaDB document collections, statistics, and search functionality.

**Base URL**: `http://localhost:8000/api/constitutional`

## Endpoints

### 1. Health Check
**GET** `/api/constitutional/health`

Check ChromaDB connection status and collection counts.

```bash
curl http://localhost:8000/api/constitutional/health | jq .
```

**Response**:
```json
{
  "status": "healthy",
  "chromadb_connected": true,
  "collections": {
    "riksdag_documents": 10,
    "swedish_gov_docs": 304871,
    "riksdag_documents_p1": 230143
  },
  "timestamp": "2025-12-15T21:58:19.657903"
}
```

---

### 2. Overview Statistics
**GET** `/api/constitutional/stats/overview`

Get overview statistics including total documents, collection counts, and storage size.

```bash
curl http://localhost:8000/api/constitutional/stats/overview | jq .
```

**Response**:
```json
{
  "total_documents": 535024,
  "collections": {
    "riksdag_documents": 10,
    "swedish_gov_docs": 304871,
    "riksdag_documents_p1": 230143
  },
  "storage_size_mb": 16087.57,
  "last_updated": "2025-12-15T21:58:24.197467"
}
```

---

### 3. Documents by Type
**GET** `/api/constitutional/stats/documents-by-type`

Get document counts grouped by document type (prop, mot, sou, bet, ds, other).

```bash
curl http://localhost:8000/api/constitutional/stats/documents-by-type | jq .
```

**Response**:
```json
[
  {
    "doc_type": "prop",
    "count": 125430,
    "percentage": 23.45
  },
  {
    "doc_type": "mot",
    "count": 98234,
    "percentage": 18.36
  }
]
```

**Note**: This endpoint processes metadata from all documents. May take 10-30 seconds for large collections.

---

### 4. Timeline Statistics
**GET** `/api/constitutional/stats/timeline`

Get document additions over the last 30 days.

```bash
curl http://localhost:8000/api/constitutional/stats/timeline | jq .
```

**Response**:
```json
[
  {
    "date": "2025-11-15",
    "count": 1234
  },
  {
    "date": "2025-11-16",
    "count": 2156
  }
]
```

---

### 5. List Collections
**GET** `/api/constitutional/collections`

List all ChromaDB collections with document counts and metadata fields.

```bash
curl http://localhost:8000/api/constitutional/collections | jq .
```

**Response**:
```json
[
  {
    "name": "riksdag_documents_p1",
    "document_count": 230143,
    "metadata_fields": [
      "title",
      "doc_type",
      "source",
      "date",
      "gdpr_clean",
      "classification",
      "sfs_refs"
    ]
  }
]
```

---

### 6. Search Documents
**POST** `/api/constitutional/search`

Search documents using semantic search with ChromaDB.

**Request Body**:
```json
{
  "query": "förvaltningslagen",
  "filters": {
    "doc_type": "prop",
    "source": "riksdagen",
    "date_from": "2024-01-01",
    "date_to": "2024-12-31"
  },
  "page": 1,
  "limit": 10,
  "sort": "relevance"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/api/constitutional/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "förvaltningslagen",
    "limit": 5,
    "page": 1
  }' | jq .
```

**Response**:
```json
{
  "results": [
    {
      "id": "doc_123",
      "title": "Proposition 2024/25:87",
      "source": "riksdagen",
      "doc_type": "prop",
      "snippet": "Regeringen föreslår ändringar i förvaltningslagen...",
      "score": 0.8924,
      "date": "2024-11-15"
    }
  ],
  "total": 156,
  "page": 1,
  "limit": 5,
  "query": "förvaltningslagen"
}
```

**Parameters**:
- `query` (required): Search query text
- `filters.doc_type`: Filter by document type (prop, mot, sou, bet, ds)
- `filters.source`: Filter by source (riksdagen, etc.)
- `filters.date_from`: Filter documents from date (YYYY-MM-DD)
- `filters.date_to`: Filter documents to date (YYYY-MM-DD)
- `page`: Page number (default: 1)
- `limit`: Results per page (1-100, default: 10)
- `sort`: Sort order ("relevance" or "date")

---

### 7. Admin Status
**GET** `/api/constitutional/admin/status`

Get comprehensive admin status including ChromaDB, PDF cache, and harvest information.

```bash
curl http://localhost:8000/api/constitutional/admin/status | jq .
```

**Response**:
```json
{
  "chromadb_status": "connected",
  "chromadb_path": "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
  "pdf_cache_size_mb": 20067.84,
  "pdf_cache_files": 7537,
  "last_harvest": {
    "status": "available",
    "file_path": "/home/ai-server/.claude/skills/swedish-gov-scraper/HARVEST_STATE.md",
    "note": "See HARVEST_STATE.md for details"
  },
  "collections": [
    {
      "name": "riksdag_documents_p1",
      "document_count": 230143,
      "metadata_fields": ["title", "doc_type", "source", "date"]
    }
  ]
}
```

---

### 8. WebSocket: Live Harvest Progress
**WebSocket** `ws://localhost:8000/api/constitutional/ws/harvest`

Subscribe to live harvest progress updates.

**Example (JavaScript)**:
```javascript
const ws = new WebSocket('ws://localhost:8000/api/constitutional/ws/harvest');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`${data.stage}: ${data.progress}% - ${data.message}`);
};
```

**Message Format**:
```json
{
  "stage": "Fetching documents",
  "progress": 25,
  "message": "Downloading from riksdagen.se..."
}
```

**Note**: Currently returns mock data. Will be integrated with actual harvest process.

---

## Current Statistics

**As of 2025-12-15**:
- Total Documents: **535,024**
- ChromaDB Storage: **16.09 GB**
- PDF Cache: **20.07 GB** (7,537 files)

**Collections**:
| Collection | Documents |
|------------|-----------|
| swedish_gov_docs | 304,871 |
| riksdag_documents_p1 | 230,143 |
| riksdag_documents | 10 |

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200 OK`: Success
- `500 Internal Server Error`: ChromaDB error or processing failure
- `503 Service Unavailable`: ChromaDB not available

**Degraded Mode**: If ChromaDB is unavailable, health endpoint returns:
```json
{
  "status": "degraded",
  "chromadb_connected": false,
  "collections": {},
  "timestamp": "2025-12-15T21:58:19.657903"
}
```

---

## Integration with Constitutional Dashboard

The dashboard frontend connects to these endpoints:

```typescript
const API_BASE = 'http://localhost:8000/api/constitutional';

// Fetch overview stats
const stats = await fetch(`${API_BASE}/stats/overview`).then(r => r.json());

// Search documents
const results = await fetch(`${API_BASE}/search`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query: 'förvaltningslagen', limit: 10 })
}).then(r => r.json());
```

---

## Performance Notes

- **Health check**: < 100ms
- **Overview stats**: < 200ms
- **Collections listing**: < 500ms
- **Search**: 1-3 seconds (depends on query complexity)
- **Documents by type**: 10-30 seconds (full metadata scan)
- **Timeline**: 10-30 seconds (full metadata scan)

**Optimization**: Documents-by-type and timeline endpoints scan metadata. Consider caching for production use.

---

## Development

**File Location**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend/app/api/constitutional_routes.py`

**Dependencies**:
- FastAPI
- ChromaDB
- Pydantic

**Testing**:
```bash
# Restart backend to apply changes
systemctl --user restart constitutional-ai-backend

# Test health endpoint
curl http://localhost:8000/api/constitutional/health | jq .
```

**API Documentation**: http://localhost:8000/docs#/constitutional

---

## Next Steps

1. Implement actual search with embeddings (currently returns empty results)
2. Add caching for expensive operations (documents-by-type, timeline)
3. Integrate WebSocket with actual harvest process
4. Add authentication/rate limiting for production
5. Add document detail endpoint (`GET /documents/{id}`)
6. Add bulk export functionality
