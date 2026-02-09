# System Status Report - 2026-01-04

## 🚨 CRITICAL FINDING: RAG SYSTEM IS BROKEN

### Backend Chaos

You have **THREE backends** and ALL have problems:

| Backend | Location | Port | Status | Problem |
|----------|-----------|-------|--------|---------|
| **OLD** | `/02_SIMONS-AI-BACKEND/` | 8000 | Running | ❌ No constitutional routes, frontends can't query |
| **NEW** | `/09_CONSTITUTIONAL-AI/backend/` | 8900 | Running | ❌ Embedding dimension mismatch (384 vs 768), returns 0 results |
| **DUPLICATE** | `/09_CONSTITUTIONAL-AI/app/` | - | Not running | ❌ Copy of OLD backend, unused |

### Systemd Service

- `constitutional-ai-backend.service`: **FAILED 1285 times**
- Tries to run `/backend/` on port 8000
- Port 8000 is occupied by OLD backend
- Service in restart loop for HOURS

### Frontend Configuration

All frontends configured to use **port 8000**:
- `apps/constitutional-gpt/src/config/env.ts`: `http://localhost:8000`
- `apps/constitutional-dashboard/src/types/index.ts`: `http://localhost:8000`

**Problem**: Port 8000 (OLD backend) doesn't have `/api/constitutional/` routes!
- Frontends can't query RAG system
- Search doesn't work
- Agent queries don't work

### ChromaDB Collections

Collections exist (535,039 docs total):
- `swedish_gov_docs`: 304,871 docs
- `riksdag_documents_p1`: 230,143 docs
- `sfs_lagtext`: 3,015 docs
- `riksdag_documents`: 10 docs

### Embedding Dimension Mismatch

**CRITICAL BUG**: NEW backend trying to use wrong embedding dimension!

```python
# NEW backend tries to use:
Expected: 384 dimensions

# ChromaDB collection uses:
Actual: 768 dimensions (KBLab/sentence-bert-swedish-cased)
```

Result: **All RAG queries return 0 results!**

---

## 🎯 ROOT CAUSE

The NEW backend (`/backend/`) was created to be the "clean" Constitutional AI backend, but:
1. It's configured to use wrong embedding model
2. It's running on port 8900, not 8000
3. Frontends are still pointing to OLD backend
4. OLD backend doesn't have constitutional routes

**Result**: RAG system completely non-functional!

---

## 📋 IMMEDIATE ACTIONS NEEDED

### P0 - Fix RAG System (DO THIS FIRST)

1. **Stop failing systemd service**
   ```bash
   systemctl --user stop constitutional-ai-backend
   systemctl --user disable constitutional-ai-backend
   ```

2. **Fix NEW backend embedding dimension**
   - Change embedding model to `KBLab/sentence-bert-swedish-cased` (768 dims)
   - Or re-embed all documents with 384-dim model

3. **Route frontend to NEW backend**
   - Change all frontend configs from port 8000 → 8900
   - Or move NEW backend to port 8000

4. **Verify RAG works**
   - Test search endpoint
   - Test agent query
   - Verify results are returned

### P1 - Backend Cleanup (AFTER RAG WORKS)

5. **Decide which backend to keep**
   - If NEW backend works → Delete OLD backend
   - If OLD backend preferred → Fix it and delete NEW

6. **Update systemd service**
   - Point to correct backend directory
   - Use correct port
   - Enable service

7. **Remove duplicate backend**
   - Delete `/app/` (copy of OLD backend)

### P2 - Documentation & Code Cleanup (AFTER RAG WORKS)

8. Fix all documentation paths and references
9. Delete temporary scripts and old code
10. Remove experimental frontend apps
11. Consolidate documentation

---

## ⚠️ WARNING: DO NOT PROCEED WITH CLEANUP YET

**RAG system is currently broken!**
- Queries return 0 results
- Frontends can't access RAG routes
- System not functional

**Fix RAG first, then cleanup!**

---

## 📊 Current Service State

```
Port 8000: OLD backend (Simons AI) - Running
  ❌ No /api/constitutional/ routes
  ❌ Frontends pointing here but can't query

Port 8900: NEW backend (Constitutional AI) - Running
  ❌ Wrong embedding dimension (384 vs 768)
  ❌ All queries return 0 results
  ✅ Has constitutional routes

Port 11434: Ollama - Running
  ✅ Models available: ministral-3:14b, gpt-sw3:6.7b

ChromaDB: Connected
  ✅ 535,039 documents indexed
  ❌ Embedding dimension mismatch
```

---

## Next Steps

1. **STOP**: Don't delete anything yet
2. **FIX**: RAG system must work first
3. **VERIFY**: Test all queries return results
4. **THEN**: Clean up backends and documentation

---

**Generated**: 2026-01-04
**Severity**: CRITICAL
**Action Required**: Fix RAG system before any cleanup
