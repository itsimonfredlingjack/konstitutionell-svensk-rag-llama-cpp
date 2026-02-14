# Reindex Runbook (Migration 2026)

## Syfte

Denna runbook beskriver exakt kommandosekvens för full re-indexering till Jina v3-embeddings samt efterföljande validering.

## Förutsättningar

- Körs från repo-roten: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI`
- Backend-venv finns på `backend/venv`
- ChromaDB-data finns lokalt på `chromadb_data`
- `constitutional-ai-llm.service` kan stoppas tillfälligt vid GPU-körning

## Senaste verifierade nulage (February 14, 2026)

- Re-indexering till `*_jina_v3_1024` ar klar och anvands i live queries
  (fallback_used:false).
- Det har forekommit intermittenta Chroma/HNSW-compactor fel i vissa collections,
  vilket kravt `chroma vacuum` och en fail-closed integrity gate innan services
  startas om.
- BM25-index finns och returnerar träffar (`data/bm25_index`, ~3.8 GB).
- Produktions-venv har nödvändiga paket (`sentence-transformers`, `rank-bm25`, `httpx`, `tqdm`).
- GPU dry-run verifierad:
  - Kommando: `backend/venv/bin/python -u scripts/reindex_corpus.py --dry-run --device gpu --batch-size 16 --collections sfs_lagtext_bge_m3_1024`
  - Resultat: 100 docs, 0 fel, `~10.40 docs/sec` total throughput.
- CPU dry-run över bredare korpus är praktiskt mycket långsam i nuvarande setup.

## 1) Pre-flight

```bash
mkdir -p logs
backend/venv/bin/pip list | grep -Ei "sentence-transformers|rank-bm25|httpx|tqdm|einops"
```

Verifiera att följande finns installerade: `sentence-transformers`, `rank-bm25`, `httpx`, `tqdm`, `einops`.

## 2) Smoke test före re-index

```bash
backend/venv/bin/python scripts/smoke_test_pipeline.py 2>&1 | tee logs/smoke_test_pre_reindex.log
```

## 3) Dry run (100 docs, inga writes)

```bash
backend/venv/bin/python scripts/reindex_corpus.py --dry-run 2>&1 | tee logs/reindex_dry_run.log
```

Om detta blir för långsamt på CPU, kör verifierande GPU dry-run på en avgränsad collection:

```bash
systemctl --user stop constitutional-ai-llm.service
backend/venv/bin/python -u scripts/reindex_corpus.py --dry-run --device gpu \
  --batch-size 16 --collections sfs_lagtext_bge_m3_1024 \
  2>&1 | tee logs/reindex_dry_run_gpu.log
systemctl --user start constitutional-ai-llm.service
```

## 4) BM25-index (om behöver byggas om)

```bash
backend/venv/bin/python scripts/build_bm25_index.py 2>&1 | tee logs/bm25_rebuild.log
du -sh data/bm25_index
```

## 5A) Full re-index på GPU (rekommenderad)

```bash
systemctl --user stop constitutional-ai-llm.service
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
backend/venv/bin/python -u scripts/reindex_corpus.py --device gpu --batch-size 64 \
  2>&1 | tee logs/reindex_full.log
systemctl --user start constitutional-ai-llm.service
```

Tips: Kör i `tmux`/`screen` för lång körning och följ progress via:

```bash
tail -f logs/reindex_full.log
```

Notera: `scripts/reindex_corpus.py` har adaptiv retry vid batch-fel (t.ex. CUDA OOM).
Skriptet halverar batch-storlek och retry:ar på samma offset för att undvika datagap.

## 5B) Full re-index på CPU (fallback)

```bash
backend/venv/bin/python scripts/reindex_corpus.py 2>&1 | tee logs/reindex_full.log
```

## 6) Smoke test efter re-index

```bash
backend/venv/bin/python scripts/smoke_test_pipeline.py 2>&1 | tee logs/smoke_test_post_reindex.log
```

## 6B) Chroma vacuum + integrity gate (om HNSW/compactor ar instabilt)

Om du ser intermittenta fel som `Error loading hnsw index` eller
`Error sending backfill request to compactor`, folj den separata runbooken:

- `scripts/CHROMA_REPAIR_RUNBOOK.md`

### Autopilot (vänta + validera automatiskt)

Om du vill att hela post-reindex-sekvensen körs automatiskt när checkpoint blir
`completed=true`, använd:

```bash
./scripts/run_post_reindex_validation.sh
```

Skriptet väntar på slutförd re-indexering och kör sedan:
- start av `constitutional-ai-llm.service`
- smoke test (med DoD gates)
- retrieval quality benchmark (med DoD gates)
- Ministral benchmark
- runtime truth-check i backend-journal
- binär cutover-kontroll: fail om fallback till `*_bge_m3_1024` upptäcks.

Miljöflaggor:
- `CUTOVER_ENFORCE_NO_FALLBACK=1` (default): fail-closed om fallback upptäcks
- `CHECKPOINT_STALE_SECONDS=600` (default): timeoutfönster för stalled re-index

## 7) Retrieval A/B benchmark (10 frågor)

```bash
backend/venv/bin/python scripts/compare_retrieval_quality.py \
  --enforce-gates \
  --output-json logs/retrieval_quality_benchmark.json
```

## 8) Ministral benchmark

```bash
backend/venv/bin/python scripts/benchmark_ministral.py 2>&1 | tee logs/benchmark_post_migration.log
```

## 9) Kvalitetskontroller

```bash
backend/venv/bin/ruff check backend/ scripts/
backend/venv/bin/pytest tests/ backend/tests -q
```

## 10) Snabb validering av resultat

- `_jina_v3_1024`-collections ska finnas i ChromaDB.
- `logs/smoke_test_post_reindex.log` ska visa non-zero dense hits.
- `logs/retrieval_quality_benchmark.json` ska innehålla latens per steg och top-5 docs per fråga.
- `logs/reindex_full.log` ska innehålla total tid, docs/sec och felräkning.
- `logs/preflight_diagnostics.log` ska inte längre visa collection fallback till `*_bge_m3_1024`.
