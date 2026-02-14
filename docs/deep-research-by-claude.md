# Optimal local RAG stack for RTX 4070 in 2026

**Your current Mistral-Nemo setup works but is no longer best-in-class.** Google's Gemma 3 12B IT and Mistral's Ministral 3 14B both represent meaningful upgrades in multilingual quality, context handling, and architecture — though each comes with practical trade-offs on 12GB VRAM. The bigger revelation: your Qwen 0.5B draft model was almost certainly never working correctly with Mistral-Nemo's unique Tekken tokenizer, meaning you were paying VRAM cost for near-zero speculative decoding benefit. Replacing the entire Chinese-origin component stack (BGE-M3, BGE-Reranker, Qwen draft) is feasible with a clean European alternative: Jina AI's embedding and reranker models match or exceed BGE quality while sharing a German origin and non-Chinese architecture. The recommended action is a phased migration — swap the LLM and draft model first, then re-index embeddings, and finally upgrade your RAG architecture with the highest-ROI improvements (cross-encoder reranking and hybrid search).

---

## The main LLM verdict: Gemma 3 12B edges out the field

Two models clearly surpass Mistral-Nemo-Instruct-2407 for multilingual RAG on 12GB VRAM in February 2026.

**Google Gemma 3 12B IT** is the top recommendation for Swedish legal documents. Trained on **12 trillion tokens** across **140+ languages** with 2× more multilingual training data than its predecessor, it uses Google's new Gemini 2.0 tokenizer optimized for non-English text. On multilingual benchmarks, it matches the much larger Gemma 2 27B while fitting comfortably in 12GB. Google's Quantization-Aware Training (QAT) produces a Q4_0 model at just **~6.6GB** for weights that preserves near-BF16 quality — a unique advantage over post-training quantization applied to other models.

**Mistral's Ministral 3 14B Instruct** (released December 2025) is the strongest alternative. At **14B parameters** with Apache 2.0 licensing, it reportedly matches Mistral Small 3.2 24B quality while fitting in 12GB at Q4_K_M (~9.2GB weights). Its **256K context window** and 40+ language support make it a serious contender, and its European origin (Mistral AI, France) aligns with the preference for non-Chinese models.

| Model | Params | Weights VRAM (Q4) | Swedish | Context | License | Origin |
|-------|--------|-------------------|---------|---------|---------|--------|
| **Gemma 3 12B IT QAT** | 12B | ~6.6 GB | ✅ 140+ langs | 128K | Gemma TOU | Google (US) |
| **Ministral 3 14B** | 14B | ~9.2 GB | ✅ 40+ langs | 256K | Apache 2.0 | Mistral (FR) |
| Mistral-Nemo 12B (current) | 12B | ~7.0 GB | ✅ Good | 128K | Apache 2.0 | Mistral/NVIDIA |
| Microsoft Phi-4 | 14B | ~9.2 GB | ❌ English-only | 16K | MIT | Microsoft (US) |
| Ministral 3 8B | 8B | ~5.0 GB | ✅ 40+ langs | 256K | Apache 2.0 | Mistral (FR) |
| Llama 3.1 8B | 8B | ~5.0 GB | ⚠️ No Swedish | 128K | Llama License | Meta (US) |

**Phi-4 is disqualified** despite excellent English benchmarks (MMLU 84.8%) — Microsoft explicitly states it is not intended for multilingual use, with only 8% non-English training data. **Llama 4 Scout** (109B MoE) and **Llama 3.3** (70B only) do not fit 12GB. European-specific models like **GPT-SW3** (AI Sweden) and **Viking** (Silo AI) are architecturally 1–2 generations behind and lack competitive instruction tuning.

### The Gemma 3 caveat you must know about

Gemma 3's interleaved local/global sliding-window attention (5:1 ratio) creates a **documented KV cache quantization bug** in llama.cpp. Enabling `--cache-type-k q8_0` causes ~10× slowdown specifically for Gemma 3 models — an issue reported across llama.cpp, koboldcpp, and Ollama with no confirmed fix as of early 2026. Without KV quantization, the f16 KV cache at 8K context consumes **~2.5–3GB**, bringing total VRAM to ~9.5–10GB with QAT Q4_0 weights. This is tight but workable. At 16K+ context, VRAM pressure becomes critical.

**Practical guidance**: Start with Gemma 3 12B QAT Q4_0 at 4–8K context (sufficient for RAG where you control chunk sizes). Test KV quantization — the bug may be resolved in recent llama.cpp builds. If VRAM remains too tight, Ministral 3 14B Q4_K_M with standard KV quantization is the fallback.

---

## Speculative decoding: your draft model was broken

**This is the most important operational finding.** Mistral-Nemo uses the unique **Tekken tokenizer** with a **131,072-token vocabulary**. Your Qwen 2.5-0.5B draft model uses a completely different tokenizer (151,643 vocab). llama.cpp requires draft and target models to share the same tokenizer — with mismatched vocabularies, acceptance rates drop to near zero, making speculative decoding actively slower than single-model inference due to the overhead of loading two models.

No small model (under 2B params) from any origin uses the Tekken tokenizer. **Mistral-Nemo has no viable draft model.** This alone is a reason to switch main models.

### The path forward depends on your main model choice

**If you choose Gemma 3 12B**: use **Gemma 3 1B IT** as draft. All Gemma 3 variants (270M, 1B, 4B, 12B, 27B) share the identical 262K-token tokenizer — confirmed by hash matching. Users on GitHub have already demonstrated this pairing with the QAT Q4_0 variants. However, Gemma family models show lower speculative acceptance rates than Llama models in benchmarks, so expect **~1.3–1.5× speedup** rather than the ~1.8× seen with Llama pairings.

**If you choose Ministral 3 14B**: the natural draft candidate is **Ministral 3B** (same 131K Tekken tokenizer). However, at ~1.8GB for Q8_0, it cannot coexist with the 14B model (~9.2GB) plus KV caches within 12GB. Use **n-gram self-speculative decoding** instead — it requires no draft model, no extra VRAM, and no tokenizer matching.

**N-gram speculation** was merged into llama.cpp via PR #18471 and works by finding repeated patterns in token history. It is free to enable alongside any model:

```bash
# N-gram speculation — no draft model, no VRAM cost
llama-server -m your-model.gguf -ngl 99 \
  --spec-type ngram-simple --draft-max 64 \
  -fa --host 0.0.0.0 --port 8080
```

For RAG workloads involving legal text with repetitive structures (statute language, templated decisions), n-gram speculation achieves **57–70% acceptance** on suitable passages. For diverse creative output, benefit is minimal.

### Recommended speculative decoding configurations

```bash
# OPTION A: Gemma 3 12B + Gemma 3 1B (best quality + speculation)
llama-server \
  -m gemma-3-12b-it-qat-q4_0.gguf \
  -md gemma-3-1b-it-q8_0.gguf \
  -c 8192 -cd 8192 \
  -ngl 99 -ngld 99 \
  --draft-max 8 --draft-min 4 --draft-p-min 0.9 \
  -fa --host 0.0.0.0 --port 8080

# OPTION B: Ministral 3 14B with n-gram only (no draft fits)
llama-server \
  -m Ministral-3-14B-Instruct-2512-Q4_K_M.gguf \
  -c 8192 -ngl 99 \
  --spec-type ngram-simple --draft-max 64 \
  -fa -ctk q8_0 -ctv q8_0 \
  --host 0.0.0.0 --port 8080
```

EAGLE-3 (the current state-of-the-art for speculative decoding, achieving 2–2.5× speedup in vLLM and SGLang) has a PR open for llama.cpp (#18039) but is not production-ready. Worth monitoring.

---

## Replacing BGE-M3 and BGE-Reranker with a clean European stack

### Embeddings: Jina Embeddings v3 is the clear replacement

**Jina Embeddings v3** (Jina AI, Berlin) is the strongest non-Chinese multilingual embedding model under 1B parameters. At **570M parameters** with 1024 dimensions and 8192-token context, it directly replaces BGE-M3's dense retrieval at equal or better quality. Swedish is in the top 30 explicitly supported languages. Its MTEB scores (English avg 65.52, multilingual avg 64.44) outperform OpenAI text-embedding-3-large and Cohere embed-v3.

Key features that make it the right choice: **five task-specific LoRA adapters** (retrieval.query, retrieval.passage, classification, separation, text-matching) enable asymmetric encoding that improves retrieval quality. **Matryoshka representation support** allows dimension reduction (down to 256) with graceful degradation for storage optimization. The XLM-RoBERTa base architecture is definitively non-Chinese.

| Embedding Model | Params | Dims | Max Tokens | Swedish | License | MTEB |
|-----------------|--------|------|------------|---------|---------|------|
| **Jina Embeddings v3** | 570M | 1024 | 8192 | ✅ Top-30 | CC-BY-NC-4.0 | 65.5 |
| Snowflake Arctic Embed L v2.0 | 568M | 1024 | 8192 | ⚠️ Cross-lingual | Apache 2.0 | ~55.6 |
| Nomic Embed v2 | 475M | 768 | 512 ⚠️ | ✅ ~100 langs | Apache 2.0 | — |
| multilingual-e5-large | 560M | 1024 | 512 ⚠️ | ✅ 70+ langs | MIT | — |

**Snowflake Arctic Embed L v2.0** (Apache 2.0) is the best fully open alternative if Jina's CC-BY-NC-4.0 license is a concern for commercial use. Nomic Embed v2 and multilingual-e5-large are disqualified by their **512-token context limits**, which are insufficient for legal document chunks.

**The hybrid retrieval gap**: BGE-M3's unique triple-mode retrieval (dense + learned sparse + ColBERT in a single model) has no direct non-Chinese equivalent. The practical workaround is a multi-component hybrid: Jina v3 for dense retrieval + BM25 (via Elasticsearch, Tantivy, or Qdrant's built-in BM25) for lexical/sparse retrieval, combined with **Reciprocal Rank Fusion**. This combination, paired with a cross-encoder reranker, **matches or exceeds** BGE-M3's standalone hybrid performance in practice.

**Re-indexing 1.37M documents**: On GPU (RTX 4070, batch mode, LLM offline), Jina v3 processes approximately **150–300 documents/second**, completing the full corpus in **~1.5–2.5 hours**. On CPU (16 cores, ONNX Runtime), expect ~15–30 docs/sec and ~15–25 hours. The 1024-dimensional output matches BGE-M3's dimensions exactly, so ChromaDB/Qdrant index structure remains compatible — you only need to re-embed, not restructure.

### Reranker: Jina Reranker v2 Base Multilingual

**Jina Reranker v2 Base Multilingual** (278M parameters, XLM-RoBERTa cross-encoder) is the cleanest non-Chinese replacement for BGE-Reranker-v2-m3. It supports **100+ languages** including Swedish, runs **15× faster throughput** than the BGE reranker, and ranks #1 on AirBench. The XLM-RoBERTa base architecture is confirmed non-Chinese origin.

**CPU reranking works well.** At ~100–200ms to rerank 20 documents on a 16-core CPU, this adds negligible latency to a RAG pipeline where LLM generation takes 2–5 seconds. Run the reranker on CPU via a separate process while the GPU handles LLM inference exclusively.

| Reranker | Params | CPU Latency (20 docs) | Multilingual | License | Origin |
|----------|--------|----------------------|--------------|---------|--------|
| **Jina Reranker v2 Base** | 278M | ~100–200ms | ✅ 100+ langs | CC-BY-NC-4.0 | Jina (DE) |
| mxbai-rerank-base-v2 | 500M | ~200–400ms | ✅ 100+ langs | Apache 2.0 | Mixedbread (DE) |
| FlashRank Nano | 4MB | ~5ms | ❌ English | Open source | Community |
| Jina Reranker v3 | 600M | ~150–300ms | ✅ Best quality | CC-BY-NC-4.0 | Jina (DE) |

**Warning about Jina Reranker v3**: Despite Jina being a German company, v3 is built on **Qwen3-0.6B** (Alibaba) as its base model — violating the Chinese-origin constraint. Similarly, **mxbai-rerank-base-v2** may use a Qwen base (verify before deploying). Jina Reranker v2 uses XLM-RoBERTa and is safe.

---

## Why you should stay with llama.cpp

There is no compelling reason to switch inference engines for a single-user RAG production setup on consumer GPU. llama.cpp has gained significant capabilities through 2025–2026 that reinforce its position:

**New capabilities that matter for your use case**: GPU token sampling (offloads sampling to GPU, reducing CPU-GPU transfers). A **router mode** (December 2025) that lets llama-server dynamically load, unload, and switch multiple models without restart — solving the multi-model management problem natively. Concurrent CUDA streams for QKV projections. Flash attention now default. **35% faster MoE token generation** on NVIDIA GPUs. N-gram self-speculative decoding. Improved structured JSON output via GBNF grammar.

**Why alternatives don't fit**: vLLM and SGLang deliver massive throughput advantages at high concurrency (35×+ RPS over llama.cpp) but at **concurrency=1, performance is comparable or llama.cpp wins on inter-token latency**. Both require safetensors (not GGUF-native), Python dependency stacks, and are designed for datacenter GPUs. ExLlamaV3 offers the fastest pure-GPU inference with its new EXL3 format but provides **no CPU offloading** — fatal for 12GB VRAM with variable-length RAG contexts. Ollama **still lacks speculative decoding support** as of February 2026. TensorRT-LLM provides ~30% speed gains on RTX 4070 but requires per-GPU model compilation with a fragile toolchain.

### Multi-model strategy using router mode

The new llama-server router mode is exactly what a CRAG system needs. Start llama-server without specifying a model, point it at a models directory, and it auto-discovers GGUFs, routing requests based on the `model` field in API calls. Each model runs in its own process with LRU eviction:

```bash
# Router mode — serves multiple models from a directory
llama-server --models-dir /path/to/models/ \
  --models-max 3 \
  --host 0.0.0.0 --port 8080
```

For the CRAG pattern specifically: use the main model for both generation and document grading. A grading call with ~200 tokens input and structured JSON output takes under 1 second. A dedicated small classifier on CPU is only worth the complexity if you're grading **10+ documents per query** and latency is critical.

**Embeddings on CPU while LLM on GPU** is the correct architecture. Run Jina v3 via a separate process with `--n-gpu-layers 0` or via ONNX Runtime on CPU. At ~50–200 tokens/sec on 16 CPU cores, this is adequate for query-time embedding. The GPU stays exclusively dedicated to LLM inference.

---

## RAG architecture upgrades worth making in 2026

Research across the RAG landscape reveals three tiers of improvements ranked by return on investment for a Swedish legal document system.

### Tier 1: Highest ROI, implement immediately

**Add cross-encoder reranking** if your CRAG pipeline doesn't already rerank retrieved results with a cross-encoder. Reranking delivers **28–48% improvement** in retrieval quality (nDCG@10) across multiple benchmarks. Retrieve top 30–50 chunks from your vector store, rerank to top 5 with Jina Reranker v2 on CPU, then feed to the LLM. This is the single most impactful change you can make to retrieval quality.

**Implement hybrid search** with Reciprocal Rank Fusion. Combine dense vector retrieval (Jina v3) with BM25 lexical search. For Swedish legal text with precise terminology ("arbetsgivarens skyldigheter", specific SFS references), BM25 captures exact matches that dense retrieval misses. If you migrate to Qdrant, hybrid search is built-in. Otherwise, add Tantivy or Elasticsearch alongside ChromaDB.

**Add query expansion**: Generate 2–3 reformulations of the user's query before retrieval. A single LLM call producing Swedish synonyms and related legal terms costs ~0.5 seconds and measurably improves recall. Low effort, high return.

### Tier 2: Structure improvements for legal documents

**Summary-Augmented Chunking (SAC)** is a 2025 technique specifically validated for legal RAG. Prepend a single document-level summary to every chunk from that document. This prevents "Document-Level Retrieval Mismatch" — retrieving correct text from the wrong law — which is a critical problem in large legal databases with structurally similar documents. At **one LLM call per document** (1.37M calls), this is feasible over a few weeks of background processing. Full Anthropic-style Contextual Retrieval (one LLM call per *chunk*) is impractical at this scale — ~13.7M LLM calls would take months on consumer hardware.

**Structure-aware chunking** for Swedish legal documents. SFS-formatted laws have well-defined hierarchies (Kapitel → Paragraf → Stycke → Punkt). Chunk at clause boundaries rather than fixed token counts, preserve hierarchy metadata, and implement parent-child retrieval — index at paragraph level but return the parent section for context.

**Legal reference graphs without GraphRAG**: Full Microsoft GraphRAG is impractical at 1.37M documents on consumer hardware (the indexing cost alone would take months of continuous LLM inference). Instead, build targeted reference structures: parse SFS cross-references ("se 5 kap. 3 § arbetsmiljölagen") using regex, construct a citation graph in NetworkX, and during retrieval pull in referenced laws alongside primary results. Build a definitions graph by extracting definitions sections from laws and auto-injecting them when defined terms appear in retrieved chunks. These cost zero LLM calls and provide high value for legal queries.

### Tier 3: Worth evaluating but lower priority

**Late chunking** (Jina AI technique) embeds the full document first using a long-context model, then applies mean pooling within chunk boundaries. This preserves cross-chunk context without additional LLM calls. With Jina v3's 8192-token window, it produces **~3.6% relative improvement** over naive chunking — modest but free of additional compute cost at query time. Consider implementing when you switch to Jina v3.

**ColBERT via RAGatouille** as a late-interaction reranker rather than primary retriever. The `answerai-colbert-small-v1` model (33M params) outperforms models 10× its size and uses only ~130MB RAM. However, ColBERT stores per-token embeddings, so indexing 13.7M chunks at ~128 dims × ~32 tokens could consume **15–30GB on disk** even with PLAID compression. Use it for reranking the top 100 results rather than as the primary index.

### Migrate ChromaDB to Qdrant at this scale

At **13.7M vectors** (1.37M documents × ~10 chunks each), ChromaDB is at the edge of its comfortable operating range. It lacks native hybrid search (BM25 + dense), sparse vector support, and sophisticated filtering. **Qdrant** (Rust-based, self-hosted) provides native hybrid search with BM25, sparse vector support for SPLADE-style retrieval, multi-vector storage (title + body embeddings), integrated pre-filtering on metadata (filter by SFS number, date, document type), and proven performance at billions of vectors with sub-30ms query latency. For a production legal RAG system, this migration is worth the effort.

---

## The recommended 2026 stack

| Component | Current | Recommended | VRAM/RAM | Change urgency |
|-----------|---------|-------------|----------|----------------|
| **Main LLM** | Mistral-Nemo-Instruct-2407 Q5_K_M | **Gemma 3 12B IT QAT Q4_0** | ~6.6 GB VRAM | High — meaningful quality upgrade |
| **Draft model** | Qwen2.5-0.5B Q8_0 (broken) | **Gemma 3 1B IT Q8_0** | ~1.1 GB VRAM | High — current draft wasn't working |
| **Embeddings** | BAAI/bge-m3 | **Jina Embeddings v3** | CPU (~2.3 GB RAM) | Medium — requires re-indexing |
| **Reranker** | BAAI/bge-reranker-v2-m3 | **Jina Reranker v2 Base Multilingual** | CPU (~560 MB RAM) | Medium — drop-in replacement |
| **Lexical search** | None | **BM25 via Qdrant or Tantivy** | Minimal | Medium — enables hybrid retrieval |
| **Vector DB** | ChromaDB | **Qdrant** (self-hosted) | ~2–4 GB RAM | Medium — scale + hybrid search |
| **Inference** | llama.cpp (llama-server) | **llama.cpp** (stay) | — | None — still best choice |
| **Backend** | FastAPI Python 3.12 | **FastAPI** (stay) | — | None |

### Total VRAM budget

```
Gemma 3 12B QAT Q4_0 weights:      ~6.6 GB
Gemma 3 1B Q8_0 draft weights:     ~1.1 GB
KV cache (f16, 8K context, main):   ~2.5 GB
KV cache (f16, 8K context, draft):  ~0.2 GB
CUDA overhead:                      ~0.5 GB
─────────────────────────────────────────────
Total:                              ~10.9 GB ← fits in 12 GB
```

### Production command line

```bash
# PRIMARY: Gemma 3 12B + 1B draft + n-gram fallback
llama-server \
  -m /models/gemma-3-12b-it-qat-q4_0.gguf \
  -md /models/gemma-3-1b-it-q8_0.gguf \
  -c 8192 -cd 8192 \
  -ngl 99 -ngld 99 \
  --draft-max 8 --draft-min 4 --draft-p-min 0.9 \
  -fa \
  --host 0.0.0.0 --port 8080

# ALTERNATIVE: Ministral 3 14B (if Gemma 3 KV issues persist)
llama-server \
  -m /models/Ministral-3-14B-Instruct-2512-Q4_K_M.gguf \
  -c 8192 -ngl 99 \
  --spec-type ngram-simple --draft-max 64 \
  -fa -ctk q8_0 -ctv q8_0 \
  --host 0.0.0.0 --port 8080

# EMBEDDINGS (separate process, CPU-only)
# Run via Python with sentence-transformers or ONNX Runtime
# Jina v3 on CPU: ~15-30 docs/sec for indexing
# Query-time embedding: ~50-200 tokens/sec (adequate for RAG)
```

---

## What to change versus what is good enough

**Change immediately**: Remove Qwen 0.5B draft model — it was never working correctly with Mistral-Nemo's tokenizer. Either switch main models to get proper speculative decoding, or enable n-gram speculation on your current Mistral-Nemo setup for a free, no-risk improvement.

**Change when ready (high value)**: Upgrade main LLM to Gemma 3 12B or Ministral 3 14B. Add cross-encoder reranking (Jina Reranker v2). Both provide substantial quality improvements with moderate migration effort.

**Change during planned maintenance**: Replace BGE-M3 embeddings with Jina v3 (requires re-indexing weekend). Replace BGE-Reranker with Jina Reranker v2 (drop-in). Migrate ChromaDB to Qdrant and implement hybrid search.

**Good enough — don't change**: llama.cpp as inference engine (still the best choice). FastAPI backend. CRAG architecture pattern (enhance it, don't replace it). Structured JSON output via grammar constraints.

**The "invisible enough" question on embeddings**: The embedding model is genuinely less visible in the stack than the LLM — end users interact with the LLM's output directly but never see which embedding model retrieved the documents. If the Chinese-origin constraint is about optics rather than strict compliance, embeddings could be deprioritized. However, if the constraint is policy-driven, Jina v3 is a clean, no-compromise replacement that actually improves retrieval quality.

---

## Six things to watch in the next six months

**Gemma 3 KV cache fix in llama.cpp** is the most important near-term development to monitor. Once the interleaved sliding-window attention KV quantization works correctly, Gemma 3 12B becomes unambiguously the best 12GB option with dramatically reduced VRAM pressure. Track llama.cpp issues #12352 and related PRs.

**EAGLE-3 in llama.cpp** (PR #18039) would deliver 2–2.5× speculative decoding speedup — significantly more than traditional draft model approaches. It trains a tiny draft head on the target model's hidden states, eliminating the need for a separate draft model entirely. This could arrive in production-ready form within months.

**Mistral's next 12B-class model** may arrive mid-2026. Mistral has been releasing models every 3–6 months, and a Nemo successor in the 12B range with the Ministral 3 architecture would combine Nemo's proven multilingual quality with newer training and architecture improvements.

**Llama 4 dense variants**: Meta's Llama 4 Scout (109B MoE, 17B active) doesn't fit consumer hardware, but Meta historically releases smaller dense variants months after initial release. A hypothetical Llama 4 8B would be highly competitive.

**Jina Embeddings v3.5 or v4 text-only**: Jina v4 exists but is built on Qwen (Chinese origin) and oriented toward multimodal. A future text-only version on a non-Chinese base would be significant. Also watch for Nomic Embed with longer context windows.

**ExLlamaV3's EXL3 format** achieves remarkable compression (Llama 3.1 70B coherent at 1.6 bits-per-weight, fitting in 16GB). If EXL3 gains CPU offloading support, it could challenge GGUF's dominance for consumer GPU inference. Currently its GPU-only requirement limits it for variable-length RAG on 12GB VRAM.
