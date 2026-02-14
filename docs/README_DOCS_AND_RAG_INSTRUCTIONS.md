# Dokumentation och RAG-instruktioner

**Senast uppdaterat:** 2026-02-13

## Kanoniska RAG-instruktioner (hur projektet ska byggas)

För **modellval, stack, retrieval-arkitektur och migrationsbeslut** gäller:

- **`docs/deep-research-by-claude.md`** – Rekommenderad 2026-stack (Jina v3, Gemma 3 / Ministral 3, n-gram speculation, hybrid search, Qdrant, etc.)
- **`docs/deep-research-by-chatgpt.md`** – Alternativ 2026-stack (Ministral 3 14B, NVIDIA NeMo Retriever som alternativ till Jina, Flash Attention, KV-cache)

AI som bygger eller ändrar RAG-stacken ska **prioritera dessa två dokument** och inte gamla analyser eller roadmap-dokument som nämner Mistral-Nemo, BGE eller gpt-sw3 som nuvarande rekommendation.

---

## Rensning genomförd (2026-02-13)

- **Arkiverade** (i `docs/archive/`): `COMPREHENSIVE_RESEARCH_ANALYSIS.md`, `CURRENT_STATE_ANALYSIS.md`, `STEG3_2_VERIFICATION.md`, `FAS1_VERIFICATION_REPORT.md`, `FAS1_IMPLEMENTATION_GUIDE.md`, `CODEX_TODO_SSE_STREAM_REFACTORING.md`.
- **Uppdaterade** till Ministral-3-14B / Jina + referens till deep-research: `docs/AGENTS.md`, `docs/DEPLOYMENT.md`, `docs/GITHUB_PUBLICATION_GUIDE.md`, `docs/system-overview.md`, `docs/BACKEND_STATUS.md`, `docs/IMPLEMENTATION_ROADMAP.md`, `docs/sprint/orchestrator-decomposition.md`.
- **CLAUDE.md**: Pekare till deep-research tillagd under Arkitektur.

---

## Automatisk validering (CI + lokalt)

För att förhindra att gamla modellreferenser återinförs i aktiva dokument finns
nu en canonicality-check:

```bash
python scripts/check_docs_canonical.py
```

Regler:
- `docs/archive/**` är undantagna.
- `docs/deep-research-by-*.md` är undantagna.
- `docs/README_DOCS_AND_RAG_INSTRUCTIONS.md` är undantagen.
- Historiska/migrationsrader med tydlig kontext (`->`, `historical`,
  `legacy`, `deprecated`, `migrat*`) tillåts.

---

## Vad som är arkiverat / föråldrat (referens)

Följande dokument innehöll **gamla** modell- eller stackreferenser (Mistral-Nemo, BGE, gpt-sw3) och ska **inte** användas som källa för "hur RAG ska byggas":

| Dokument | Problem | Rekommendation |
|----------|---------|----------------|
| `docs/AGENTS.md` | Mistral-Nemo, gpt-sw3 som modellkonfig | Uppdatera till Ministral-3-14B + peka på deep-research, eller flytta till archive |
| `docs/COMPREHENSIVE_RESEARCH_ANALYSIS.md` | Mistral-Nemo 12B, Qwen 14B, BGE | Arkivera (docs/archive/) |
| `docs/CURRENT_STATE_ANALYSIS.md` | "Mistral-Nemo optimal" | Arkivera |
| `docs/IMPLEMENTATION_ROADMAP.md` | Mistral-Nemo som "done", gpt-sw3 i tabeller | Uppdatera eller arkivera |
| `docs/DEPLOYMENT.md` | wget Mistral-Nemo, gamla modellvägar | Uppdatera till Ministral-3-14B / peka på MODEL_OPTIMIZATION |
| `docs/GITHUB_PUBLICATION_GUIDE.md` | Mistral-Nemo, gpt-sw3 | Uppdatera modellsektion |
| `docs/system-overview.md` | Mistral-Nemo | Uppdatera eller arkivera |
| `docs/BACKEND_STATUS.md` | Mistral-Nemo | Uppdatera en rad |
| `docs/CODEX_TODO_SSE_STREAM_REFACTORING.md` | Mistral-Nemo | Arkivera eller uppdatera |
| `docs/STEG3_2_VERIFICATION.md` | Mistral-Nemo | Arkivera (verifikation av gammal setup) |
| `docs/FAS1_VERIFICATION_REPORT.md`, `FAS1_IMPLEMENTATION_GUIDE.md` | Mistral-Nemo setup | Arkivera (historisk verifikation) |
| `docs/sprint/orchestrator-decomposition.md` | BGE reranking | Uppdatera till Jina eller arkivera |

---

## Dokument som stämmer med nuvarande stack (behåll)

- **`CLAUDE.md`** (root) – Projektöversikt, kommandon, pipeline; redan uppdaterad till Ministral-3-14B, Jina. (Grader: Qwen 0.5B nämns fortfarande – se deep-research om draft/grader-modeller.)
- **`docs/ARCHITECTURE.md`** – Systemarkitektur; innehåller redan Ministral-3-14B, Jina, Qwen för grading.
- **`docs/MODEL_OPTIMIZATION.md`** – Modellparametrar och migration 2026; aktuell.
- **`docs/MIGRATION_2026.md`** – Beskriver genomförd migration; bra som historik.
- **`AGENTS.md`** (root) – Allmänna repo-riktlinjer (struktur, build, style); ingen modellreferens.

---

## Sammanfattning (rensning utförd)

Rensningen är genomförd: arkiverade filer flyttade, övriga uppdaterade, och `CLAUDE.md` pekar nu på deep-research-dokumenten. För framtida RAG-stack- och modellbeslut: använd **`docs/deep-research-by-claude.md`** och **`docs/deep-research-by-chatgpt.md`**.
