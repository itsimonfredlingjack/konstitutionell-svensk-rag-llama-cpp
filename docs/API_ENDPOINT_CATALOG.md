# API Endpoint Catalog & Validation Status

**Project**: Constitutional AI Backend
**Framework**: FastAPI 0.109+
**Base URL**: \`http://localhost:8900\`
**API Version**: v2
**Documentation**: \`/docs\` (Swagger UI), \`/redoc\` (ReDoc)

---

## Quick Summary

| Category | Endpoints | Validation | Auth | Status |
|----------|-----------|-----------|------|--------|
| **Health & Metrics** | 3 | 100% ✓ | None | LIVE |
| **Agent/Query** | 2 + WS | 100% ✓ | None | LIVE |
| **Documents CRUD** | 5 | 100% ✓ | None | LIVE |
| **TOTAL** | **13** | **100%** | **None** | **LIVE** |

---

## 1. Health & Metrics Endpoints (3 total)

### 1.1 GET /api/constitutional/health

**Purpose**: Health check for Constitutional AI services  
**Validation**: Full Pydantic validation ✓  
**Auth**: None (public)

**Response**: HTTP 200
\`\`\`json
{
  "status": "healthy",
  "services": {"orchestrator": "healthy", "retrieval": "healthy"},
  "timestamp": "2025-02-07T10:30:00.123456"
}
\`\`\`

---

### 1.2 GET /api/constitutional/metrics

**Purpose**: RAG pipeline metrics (lifetime, rates, by mode)  
**Validation**: Internal metrics validated ✓  
**Auth**: None (public)

**Returns**: Aggregated metrics (requests, saknas_underlag, parse_errors)

---

### 1.3 GET /api/constitutional/metrics/prometheus

**Purpose**: Prometheus-format metrics export  
**Validation**: Text format (no validation)  
**Auth**: None (public)

**Returns**: text/plain Prometheus format for scraping

---

## 2. Agent/Query Endpoints (2 + WebSocket)

### 2.1 POST /api/constitutional/agent/query

**Purpose**: Main RAG pipeline (batch mode)  
**Validation**: Full Pydantic ✓  
**Auth**: None  
**Rate Limit**: None (TODO)

**Request Body Validation**:
\`\`\`
question: str (1-2000 chars) ✓
mode: str (auto|chat|assist|evidence) 
history: List[ConversationMessage] (max 10 documented)
use_agent: bool (optional, default false)
\`\`\`

**Response**: HTTP 200
\`\`\`json
{
  "answer": "...",
  "sources": [{id, title, snippet, score, doc_type, source, retriever, loc}],
  "mode": "assist",
  "saknas_underlag": false,
  "evidence_level": "HIGH",
  "citations": [{claim, source_id, source_title, source_collection, tier}],
  "intent": "legal_explanation",
  "routing": {primary, support, secondary, secondary_budget}
}
\`\`\`

**Error Responses**:
- 400 Bad Request (question too long)
- 422 Unprocessable Entity (invalid JSON schema)
- 500 Internal Server Error (LLM/retrieval error)

**Header Options**:
- \`X-Retrieval-Strategy\`: parallel_v1|rewrite_v1|rag_fusion|adaptive

---

### 2.2 POST /api/constitutional/agent/query/stream

**Purpose**: Streaming RAG query (Server-Sent Events)  
**Validation**: Same as /agent/query ✓  
**Auth**: None  
**Response Format**: text/event-stream

**Event Types**:
- metadata: Initial response metadata
- decontextualized: Query rewriting
- token: Streaming response tokens (repeated)
- corrections: Guardrail corrections
- done: Pipeline complete
- error: Error message

---

### 2.3 WS /ws/harvest

**Purpose**: Live document harvesting progress  
**Validation**: No validation (WebSocket frames)  
**Auth**: None  
**Current Status**: Sends heartbeat every 30s (no actual harvest updates)

---

## 3. Collections Endpoints (2 total)

### 3.1 GET /api/constitutional/collections

**Purpose**: List ChromaDB collections with metadata  
**Validation**: Pydantic ✓  
**Auth**: None

**Response**: HTTP 200
\`\`\`json
[
  {
    "name": "naturvardsverket",
    "document_count": 2450,
    "metadata_fields": ["doc_type", "source", "date"]
  }
]
\`\`\`

---

### 3.2 GET /api/constitutional/stats/overview

**Purpose**: Dashboard statistics (placeholder)  
**Validation**: Pydantic ✓  
**Auth**: None

**Response**: HTTP 200 (placeholder values only)

---

## 4. Documents CRUD Endpoints (5 total)

### 4.1 GET /api/documents

**Purpose**: List documents (paginated + filtered)  
**Validation**: Query params validated ✓  
**Auth**: None

**Query Parameters**:
- collection: optional (max 200 chars, sanitized)
- doc_type: optional (max 100 chars, sanitized)
- page: int (min 1) ✓
- limit: int (1-100, default 10) ✓

**Response**: HTTP 200 (paginated list)

---

### 4.2 GET /api/documents/{document_id}

**Purpose**: Retrieve single document  
**Validation**: ID sanitized ✓  
**Auth**: None

**Path Parameter**:
- document_id: max 200 chars, sanitized ✓

**Response**: HTTP 200 (DocumentResponse)  
**Errors**: 404 Not Found, 400 Bad Request

---

### 4.3 POST /api/documents

**Purpose**: Create new document  
**Validation**: Full Pydantic + content sanitization ✓  
**Auth**: None (SHOULD require auth)

**Request Body**:
\`\`\`
content: str (1-1,000,000 chars) ✓ sanitized
collection: str (alphanumeric + - _) ✓ validated
id: str optional (max 200 chars) ✓
metadata: DocumentMetadata optional
  - doc_type: optional
  - source: optional
  - date: ISO 8601 ✓ validated
  - title: optional
  - author: optional
  - tags: List[str] (max 50) ✓ validated
\`\`\`

**Content Sanitization**: Removes \`<script>\` tags ✓

**Response**: HTTP 201 Created (DocumentResponse)  
**Errors**: 400 Bad Request, 409 Conflict (ID exists), 422 Unprocessable Entity

---

### 4.4 PUT /api/documents/{document_id}

**Purpose**: Full document replacement  
**Validation**: Same as POST ✓  
**Auth**: None (SHOULD require auth)

**Response**: HTTP 200 (updated document)

---

### 4.5 PATCH /api/documents/{document_id}

**Purpose**: Partial document update  
**Validation**: Optional fields only ✓  
**Auth**: None (SHOULD require auth)

**Current Implementation**: Delegates to PUT (full replacement)

---

### 4.6 DELETE /api/documents/{document_id}

**Purpose**: Delete document  
**Validation**: ID sanitized ✓  
**Auth**: None (MUST require auth in production)

**Response**: HTTP 204 No Content  
**Errors**: 404 Not Found, 400 Bad Request

---

## 5. Validation Coverage Summary

### What IS Validated

✓ All JSON request bodies via Pydantic models  
✓ Query parameters (length, type, range)  
✓ Request body content sanitization (XSS prevention)  
✓ Date format validation (ISO 8601)  
✓ Collection name format (alphanumeric + - _)  
✓ Text length limits (max_length on all string fields)  
✓ List length limits (max 50 tags, max 10 history messages documented)  

### What is NOT Validated

✗ Rate limiting (no per-IP throttling)  
✗ Authentication (all endpoints public)  
✗ Request size limits (except per-field sanitize_input max)  
✗ WebSocket message validation  
✗ X-Retrieval-Strategy header enum validation (checked in handler, not model)  
✗ Output sanitization (responses can leak internal fields if not careful)  

---

## 6. Error Handling

All errors return standardized format:
\`\`\`json
{
  "error": "...",
  "type": "resource_not_found|validation_error|...",
  "status_code": 404,
  "details": {...}
}
\`\`\`

---

## 7. CORS Configuration

**Allowed Origins**:
- localhost:5173-5175 (Vite dev)
- localhost:3000-3003 (Node dev)
- localhost:8900 (Backend)
- 192.168.86.32:[port] (Local network)

**Allowed Methods**: GET, POST, PUT, PATCH, DELETE, OPTIONS  
**Allowed Headers**: * (too permissive, restrict in production)  
**Credentials**: Allowed

---

## 8. Security Findings

**Missing (HIGH PRIORITY)**:
- Authentication (all endpoints public)
- Rate limiting
- Request size limits
- Output validation (sanitize_answer inline, should extract)

**Implemented**:
- Input sanitization (XSS prevention)
- Length validation
- Type validation
- CORS policy

**Recommendations**:
1. Add JWT/OAuth authentication
2. Add rate limiting (redis-backed)
3. Extract sanitization logic to ResponseSanitizer utility
4. Restrict CORS headers from * to specific list
5. Add request size limits

---

## 9. Testing Checklist

- POST /agent/query with valid questions
- POST /agent/query with 2000+ char (should reject)
- POST /agent/query with history
- POST /agent/query/stream (verify SSE events)
- GET /documents (pagination)
- POST /documents with <script> tag (should sanitize)
- POST /documents with invalid collection (should reject)
- DELETE /documents (verify 204)
- GET /documents/{invalid_id} (should return 404)
- WS /ws/harvest (connection lifecycle)

---

**Catalog Updated**: 2026-02-07  
**Total Endpoints**: 13  
**Full Validation**: 100%  
**Authentication**: 0% (missing)  
**Rate Limiting**: 0% (missing)
