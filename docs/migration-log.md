# ChromaDB to Qdrant Migration Log

> Migration av 535K dokument från ChromaDB till Qdrant

**Date:** 2025-12-15
**Duration:** ~45 minuter
**Result:** 97.5% success rate

---

## Summary

| Metric | Value |
|--------|-------|
| Source | ChromaDB (535,024 docs) |
| Target | Qdrant (521,798 docs) |
| Missing | 13,226 docs (corruption) |
| Success Rate | 97.5% |

---

## Source Collections

| Collection | Documents | Status |
|------------|-----------|--------|
| swedish_gov_docs | 304,871 | Fully migrated |
| riksdag_documents_p1 | 230,143 | 94% migrated |
| riksdag_documents | 10 | Fully migrated |

---

## Migration Process

### 1. Initial Setup
```bash
# Verify ChromaDB collections
python3 -c "
import chromadb
client = chromadb.PersistentClient(path='./chromadb_data')
for c in client.list_collections():
    print(f'{c.name}: {client.get_collection(c.name).count():,}')
"
```

### 2. Run Migration
```bash
python3 chromadb_to_qdrant.py
```

### 3. Retry with Smaller Batches
```bash
# For corrupted segments
python3 chromadb_to_qdrant.py --collection riksdag_documents_p1 --batch-size 100
```

---

## Issues Encountered

### ChromaDB Internal Error
```
Error executing plan: Internal error: Error finding id
```

**Affected ranges:**
- 12,000 - 25,000
- 35,000 - 42,000
- 66,000 - 69,000

**Cause:** Index corruption in ChromaDB, likely from interrupted write operations.

**Workaround:** ID-based fetching instead of offset-based pagination.

---

## Migration Script Features

### chromadb_to_qdrant.py

```python
# Key features:
# 1. ID-based fetching (avoids offset bugs)
# 2. Retry logic (3 attempts per batch)
# 3. Skip existing documents
# 4. Progress reporting every 10K docs
# 5. Deterministic point IDs via MD5 hash
```

**Usage:**
```bash
# Full migration
python3 chromadb_to_qdrant.py

# Single collection
python3 chromadb_to_qdrant.py --collection swedish_gov_docs

# Dry run
python3 chromadb_to_qdrant.py --dry-run

# Reset Qdrant collection
python3 chromadb_to_qdrant.py --reset
```

---

## Verification

### Check Final Count
```bash
curl -s http://localhost:6333/collections/documents | jq '.result.points_count'
# Result: 521798
```

### Test Search
```bash
constitutional search "GDPR" --direct --top-k 5
```

---

## Data Integrity

### Preserved Fields
- `text` - Full document text
- `source` - Collection name
- `original_id` - ChromaDB document ID
- All metadata fields

### Point ID Generation
```python
def generate_point_id(source: str, doc_id: str) -> str:
    combined = f"{source}:{doc_id}"
    return hashlib.md5(combined.encode()).hexdigest()
```

---

## Recovery Options for Missing 13K Docs

1. **Re-scrape from Riksdagen API**
   - Documents can be re-downloaded
   - Would require identifying specific doc_ids

2. **Restore from older backup**
   - If pre-corruption backup exists
   - USB backup was already used

3. **Accept loss**
   - 2.5% loss is acceptable
   - All major document types covered

---

## Lessons Learned

1. **Offset-based pagination unreliable** in ChromaDB for large collections
2. **ID-based fetching** more robust
3. **Smaller batch sizes** help isolate corruption
4. **Progress tracking** essential for long migrations
5. **Backup before migration** - we had USB backup available

---

## Related

- [[constitutional-cli]] - CLI with direct Qdrant search
- [[system-overview]] - Architecture overview
- [[corpus-bridge]] - Import pipeline
