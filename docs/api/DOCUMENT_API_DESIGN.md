# Document Management API Design

## Overview

This document describes the RESTful Document Management API endpoint designed following FastAPI best practices. The API provides full CRUD (Create, Read, Update, Delete) operations for managing documents in ChromaDB collections.

**Base URL**: `/api/documents`  
**API Version**: 1.0.0  
**Content-Type**: `application/json`

---

## Design Summary

### RESTful Principles ✅
- Proper HTTP methods (GET, POST, PUT, PATCH, DELETE)
- RESTful resource naming (`/api/documents`)
- Appropriate HTTP status codes (200, 201, 204, 400, 404, 500)
- Content negotiation (JSON request/response)

### Request/Response Design ✅
- Consistent response structure
- Pagination support (`page`, `limit` parameters)
- Filtering (collection, doc_type)
- Pydantic validation models
- Standardized error format

### Validation & Security ✅
- Input sanitization (XSS prevention)
- Collection name validation
- Field validators (dates, tags, lengths)
- SQL injection prevention
- ⚠️ Authentication: To be implemented
- ⚠️ Rate limiting: To be implemented

### Error Handling ✅
- Standardized error response format
- Appropriate HTTP status codes
- Clear error messages (no internal exposure)
- Error codes for programmatic handling

### Documentation ✅
- OpenAPI/Swagger schema
- Parameter descriptions
- Example requests/responses
- Test cases

---

## Endpoints

### 1. List Documents
**GET** `/api/documents`

Query parameters: `collection`, `doc_type`, `page`, `limit`

### 2. Get Document
**GET** `/api/documents/{document_id}`

Query parameters: `collection` (optional)

### 3. Create Document
**POST** `/api/documents`

Request body: `DocumentCreate` model

### 4. Update Document (Full)
**PUT** `/api/documents/{document_id}`

Request body: `DocumentUpdate` model

### 5. Partially Update Document
**PATCH** `/api/documents/{document_id}`

Request body: `DocumentUpdate` model (partial)

### 6. Delete Document
**DELETE** `/api/documents/{document_id}`

Query parameters: `collection` (optional)

---

## Test Cases

### Success Scenarios
1. ✅ Create document with valid data → 201 Created
2. ✅ Get existing document → 200 OK
3. ✅ List documents with pagination → 200 OK
4. ✅ Update document (PUT) → 200 OK
5. ✅ Partially update document (PATCH) → 200 OK
6. ✅ Delete document → 204 No Content

### Error Scenarios
1. ✅ Create with invalid collection name → 400 Bad Request
2. ✅ Create with duplicate ID → 409 Conflict
3. ✅ Get non-existent document → 404 Not Found
4. ✅ Update non-existent document → 404 Not Found
5. ✅ Delete non-existent document → 404 Not Found
6. ✅ Invalid date format → 400 Bad Request
7. ✅ Too many tags (>50) → 400 Bad Request
8. ✅ XSS attempt (script tags) → Sanitized

---

## Implementation Files

- **Route Handler**: `/backend/app/api/document_routes.py`
- **Registered in**: `/backend/app/main.py`
- **OpenAPI Schema**: Available at `/docs` endpoint

---

## Usage Examples

### Create Document
```bash
curl -X POST "http://localhost:8900/api/documents" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Document content...",
    "collection": "legal_documents",
    "metadata": {
      "doc_type": "law",
      "title": "Example Law"
    }
  }'
```

### Get Document
```bash
curl -X GET "http://localhost:8900/api/documents/doc_123"
```

### List Documents
```bash
curl -X GET "http://localhost:8900/api/documents?collection=legal_documents&page=1&limit=10"
```

### Update Document
```bash
curl -X PATCH "http://localhost:8900/api/documents/doc_123" \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "title": "Updated Title"
    }
  }'
```

### Delete Document
```bash
curl -X DELETE "http://localhost:8900/api/documents/doc_123"
```

---

## Next Steps

1. **Authentication**: Implement JWT-based authentication
2. **Rate Limiting**: Add rate limiting middleware
3. **Authorization**: Implement RBAC for collection-level permissions
4. **Caching**: Add response caching for GET operations
5. **Audit Logging**: Log all document operations
6. **Batch Operations**: Add bulk create/update/delete endpoints
