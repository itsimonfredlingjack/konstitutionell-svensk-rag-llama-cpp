# Migration 2026

## Översikt

Detta dokument sammanfattar migreringen av Constitutional AI till den nya RAG-stacken under 2026, inklusive modellbyten, retrieval-förbättringar och driftkrav.

## Vad som bytts

- **LLM**: Mistral-Nemo-Instruct-2407 -> Ministral-3-14B-Instruct-2512
- **Embeddings**: BGE-M3 -> Jina Embeddings v3 (`jinaai/jina-embeddings-v3`)
- **Reranker**: BGE Reranker -> Jina Reranker v2 (`jinaai/jina-reranker-v2-base-multilingual`)
- **Draft setup**: Qwen draft-modell borttagen från huvudflödet

## Vad som lagts till

- N-gram-speculation i kompatibla llama-server builds
- Hybrid search: Dense + BM25
- Reciprocal Rank Fusion (RRF)
- Query expansion (3 reformuleringar per fråga)
- GBNF grammar constraints för graderingsoutput

## Benchmark och verifiering

Följande loggar används som primära referenser:

- `logs/smoke_test_pre_reindex.log`
- `logs/reindex_dry_run.log`
- `logs/reindex_full.log` (när full körning har genomförts)
- `logs/smoke_test_post_reindex.log`
- `logs/retrieval_quality_benchmark.json`
- `logs/benchmark_post_migration.log`

Ministral-baseline före migrationen av retrieval-lagret:

- Throughput: ~62-73 tok/s
- TTFT: ~94-109 ms

Efter migration ska samma mätpunkter rapporteras tillsammans med latenspåslag från query expansion, reranking och grading.

## Kända begränsningar

- Re-indexering krävs vid embedding-modellbyte (vektorrummet är inkompatibelt mellan BGE och Jina).
- BM25-index måste byggas om när korpus ändras väsentligt.
- N-gram-speculation beror på stöd i aktuell `llama-server`-build och flaggkompatibilitet.

## Driftnoteringar

- GPU-reindex kräver att `llama-server` stoppas temporärt för att frigöra VRAM.
- CPU-reindex är långsammare men kan köras utan stopp av LLM-tjänsten.
- Query expansion är fail-open och får inte blockera retrieval vid parser/LLM-fel.

## Operational done criteria

Använd checklistan nedan innan migreringen markeras som driftmässigt färdig.

- [ ] Dense retrieval kör mot `*_jina_v3_1024` utan fallback till `*_bge_m3_1024`.
- [ ] `cutover_enforce_jina_collections=true` är aktiverad efter verifierad cutover.
- [ ] BM25-index är populerat och returnerar träffar för smoke test-frågor.
- [ ] Query expansion är verifierad (grammar + fallback-parser).
- [ ] Reranker i runtime är `jinaai/jina-reranker-v2-base-multilingual`.
- [ ] Live smoke test före och efter re-indexering är loggat i `logs/`.
- [ ] `scripts/compare_retrieval_quality.py --enforce-gates` returnerar PASS.
- [ ] `scripts/smoke_test_pipeline.py --enforce-gates` returnerar PASS.

## Framtida arbete

- Qdrant-migrering för skalbar vektorsökning
- SAC (Summary-Augmented Chunking)
- Structure-aware chunking för SFS-format
- Legal reference graph (lagrum <-> förarbeten <-> praxis)
