# Chroma repair runbook (vacuum + integrity gate)

This runbook documents the fail-closed sequence that makes ChromaDB
release-safe after intermittent HNSW/compactor errors. If the integrity gate
fails, do not restart the backend or LLM.

Repo root: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI`

## When to run vacuum

Run vacuum when you see intermittent errors like:

- `Error sending backfill request to compactor ...`
- `Error loading hnsw index`
- `Error constructing hnsw segment reader`

In practice, these have been most common in:

- `swedish_gov_docs_jina_v3_1024`
- `diva_research_jina_v3_1024`

## Standard sequence (GO/NO-GO)

Follow these steps in order:

1. Stop services so `chromadb_data` is released:

   ```bash
   systemctl --user stop constitutional-ai-backend.service constitutional-ai-llm.service
   ```

2. Run vacuum (this can take a long time):

   ```bash
   backend/venv/bin/chroma vacuum --path chromadb_data --force --timeout 14400
   ```

3. Run the post-vacuum gate runner (fail-closed):

   ```bash
   ./scripts/run_post_vacuum_gate.sh
   ```

The runner writes all logs under `logs/`, including:

- `post_vacuum_gate_*.log` (master log)
- `chroma_integrity_gate_*.log` and `chroma_integrity_report_*.json`
- `smoke_test_post_vacuum_*.log` and `smoke_test_post_vacuum_*.json`
- `retrieval_quality_post_vacuum_*.log` and `retrieval_quality_post_vacuum_*.json`
- `runtime_truth_post_vacuum_*.json`

## GO/NO-GO criteria

GO means it's safe to restart services and run benchmarks:

- `scripts/chroma_integrity_check.py` exits `0`
- No HNSW/compactor errors appear in the backend journal during the run window
- The runtime truth snapshot is green:
  - `resolved_collection[*].resolved` ends with `*_jina_v3_1024`
  - `fallback_used` is `false`

NO-GO means you stop. The runner does this automatically:

- Any integrity query triggers an exception
- Any integrity query returns empty results unexpectedly (`count > 0`, but `ids` is empty)
- Any HNSW/compactor strings are detected in the backend journal during gating

## Rollback plan on FAIL (isolated rebuild)

The goal is an isolated rebuild for only the failing collections.

1. Identify failing collections in:
   - `logs/chroma_integrity_report_*.json`
   - `logs/chroma_integrity_gate_*.log`

2. Rebuild only the failing collection(s).

   If the corresponding source `*_bge_m3_1024` collection still exists, rebuild
   from it (recommended because it avoids reading from the possibly broken
   `*_jina_v3_1024` target):

   ```bash
   backend/venv/bin/python -u scripts/reindex_corpus.py \
     --collections swedish_gov_docs_bge_m3_1024
   ```

   If there is no legacy source collection, you can attempt an in-place rebuild
   of the target collection:

   ```bash
   backend/venv/bin/python -u scripts/reindex_corpus.py \
     --collections swedish_gov_docs_jina_v3_1024
   ```

3. Run vacuum again.

4. Re-run `./scripts/run_post_vacuum_gate.sh`.

## Cutover (fail-closed against BGE fallback)

Enable cutover enforcement only after vacuum plus integrity gate has passed
stably.

Set this in `backend/.env`:

```bash
CONST_CUTOVER_ENFORCE_JINA_COLLECTIONS=true
```

Then restart the backend:

```bash
systemctl --user restart constitutional-ai-backend.service
```

If anything breaks, set the value back to `false` and restart again.
