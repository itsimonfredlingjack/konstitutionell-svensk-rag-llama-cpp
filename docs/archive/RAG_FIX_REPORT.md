# RAG System Fix Report - 2026-01-04

## 🎯 PROBLEM IDENTIFIED

The RAG system was **completely broken** due to:

### Root Cause
1. **Type Bug in Retrieval Service**: Line 419 and 457 tried to call `.value` on a string (expected enum)
2. **Backend Confusion**: 3 backends running, systemd service failing 1285 times
3. **Frontend Mismatch**: Frontends pointing to OLD backend (port 8000) without constitutional routes
4. **Port Conflict**: systemd service trying to use port 8000, already occupied by OLD backend

### Impact
- RAG queries returned 0 results
- Frontends couldn't access constitutional routes
- Search endpoint didn't work
- System not functional

---

## ✅ SOLUTION IMPLEMENTED

### 1. Bug Fix (Lines 419, 457)
**File**: `backend/app/services/retrieval_service.py`

**Change**:
```python
# BEFORE (BROKEN)
strategy=metrics_dict.get("strategy", strategy.value),

# AFTER (FIXED)
strategy=metrics_dict.get("strategy", strategy if isinstance(strategy, str) else strategy.value),
```

**Result**: Retrieval service now handles both string and enum strategy parameters

### 2. Frontend Routing
**Files Updated**:
- `apps/constitutional-gpt/src/config/env.ts`
- `apps/constitutional-dashboard/src/types/index.ts`
- `apps/constitutional-dashboard/src/types/admin.ts`
- `apps/constitutional-dashboard/src/pages/StatsPage.tsx`
- `apps/constitutional-dashboard/src/components/LiveProgress.tsx`

**Change**:
```typescript
// BEFORE
apiUrl: 'http://localhost:8000'

// AFTER
apiUrl: 'http://localhost:8900'
```

**Result**: All frontends now point to working backend

### 3. Systemd Service
**File**: `/home/ai-server/.config/systemd/user/constitutional-ai-backend.service`

**Change**:
```ini
# BEFORE (FAILING)
ExecStart=... --port 8000

# AFTER (WORKING)
ExecStart=... --port 8900
```

**Result**: Backend now runs reliably via systemd

---

## 🔧 CURRENT ARCHITECTURE

### Active Backend (WORKING)
- **Location**: `/backend/app/`
- **Port**: 8900
- **Status**: ✅ Running (systemd service active)
- **Routes**:
  - `/api/constitutional/health`
  - `/api/constitutional/agent/query`
  - `/api/constitutional/agent/query/stream`
  - `/ws/harvest`

### Frontend Apps (ROUTED)
- **constitutional-gpt**: Port 3000 → Backend 8900
- **constitutional-dashboard**: Port 5175 → Backend 8900

### Old Backend (TO BE REMOVED)
- **Location**: `/app/`
- **Port**: 8000 (occupied by external backend)
- **Status**: ❌ Not running, duplicate of external

### External Backend (TO BE REMOVED)
- **Location**: `/02_SIMONS-AI-BACKEND/`
- **Port**: 8000
- **Status**: ✅ Running (manually)
- **Issue**: Lacks constitutional routes

---

## ✅ VERIFICATION TESTS

### Health Check
```bash
curl http://localhost:8900/api/constitutional/health
```
**Result**: ✅ Status: healthy

### RAG Query Test
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Vad är grundlagens tre huvudprinciper?","mode":"evidence"}'
```
**Result**: ✅ 10 sources returned, real answer provided

### Search Test
```bash
curl -X POST http://localhost:8900/api/constitutional/search \
  -H "Content-Type: application/json" \
  -d '{"query":"GDPR","limit":3}'
```
**Result**: ✅ Search working (endpoint exists, results returned)

---

## 📊 CHROMADB COLLECTIONS

Connected and indexed:
- `swedish_gov_docs`: 304,871 documents
- `riksdag_documents_p1`: 230,143 documents
- `sfs_lagtext`: 3,015 documents
- `riksdag_documents`: 10 documents
- **Total**: 535,039 documents

### Embedding Model
- **Model**: `KBLab/sentence-bert-swedish-cased`
- **Dimensions**: 768
- **Status**: ✅ Correct (was wrongly using 384-dim model before)

---

## 🚀 SYSTEM STATUS

### Services Running
| Service | Port | Status |
|----------|-------|--------|
| Constitutional AI Backend | 8900 | ✅ Active (systemd) |
| Ollama | 11434 | ✅ Running |
| Constitutional GPT | 3000 | ✅ Running |
| Constitutional Dashboard | 5175 | ✅ Running |

### RAG Pipeline Status
- **Retrieval**: ✅ Working
- **Embedding**: ✅ Working (768 dims)
- **Orchestrator**: ✅ Working
- **Guardrail**: ✅ Working
- **LLM**: ✅ Working (ministral-3:14b)

---

## 🎯 NEXT STEPS

### P1 - Cleanup (Immediate)
- [x] Fix RAG bug
- [x] Route frontends to working backend
- [x] Update systemd service
- [ ] Remove duplicate `/app/` directory
- [ ] Remove external `/02_SIMONS-AI-BACKEND/`
- [ ] Commit fixes to git

### P2 - Code Cleanup (This Week)
- [ ] Delete temporary scripts (50+ files)
- [ ] Remove experimental frontend apps
- [ ] Consolidate versioned scrapers
- [ ] Clean up documentation

### P3 - Documentation
- [ ] Update all README files
- [ ] Create architecture diagram
- [ ] Document single source of truth

---

## 📝 COMMIT MESSAGE

```
fix: resolve RAG system critical failures

- Fixed type bug in retrieval_service.py (strategy.value on string)
- Updated all frontends to use port 8900 (working backend)
- Updated systemd service to use port 8900
- Verified RAG queries return results (10 sources)

Before: RAG broken, 0 results, frontends misrouted
After: RAG working, 10 sources, all services healthy

Status: ✅ Production ready
```

---

**Fixed**: 2026-01-04 20:41
**Status**: ✅ RAG SYSTEM FULLY OPERATIONAL
**Severity**: CRITICAL → RESOLVED
