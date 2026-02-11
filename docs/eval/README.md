# Evaluation Framework

## Overview

Constitutional-AI använder **RAGAS** (Retrieval-Augmented Generation Assessment) för att mäta RAG-kvalitet.

### Varför RAGAS?

- **Standardiserade mått**: Jämförbara över tid
- **LLM-baserad verifiering**: Mäter faktisk kvalitet, inte bara keyword-overlap
- **Etablerat ramverk**: Används av OpenAI, Anthropic, m.fl.
- **Kapslat**: Kan bytas till lightweight senare

---

## Mått

### 1. Faithfulness (Trovärdighet)

**Vad**: Mäter om svaret stöds av kontext (ingen hallucination).

**Hur**: 
1. Extrahera claims från svar
2. Verifiera varje claim mot kontext
3. Score = claims_supported / total_claims

**Exempel**:
```
Svar: "RF 2 kap. 1 § garanterar yttrandefrihet."
Kontext: "RF 2 kap. 1 § säger att var och en är tillförsäkrad yttrandefrihet."
→ Faithfulness: 1.0 (100% stöd)
```

**Målvärde**: ≥ 0.8 (80% av claims stöds)

---

### 2. Context Precision (Kontextprecision)

**Vad**: Mäter om relevanta chunks rankas högt.

**Hur**:
1. Identifiera vilka chunks som är relevanta (via ground truth)
2. Kolla var de hamnar i rankningen
3. Score = weighted precision@k

**Exempel**:
```
Query: "Vad säger RF om yttrandefrihet?"
Chunks: [RF 2 kap. 1 §, RF 2 kap. 2 §, OSL 21 kap., ...]
→ Relevanta chunks är i toppen → Hög precision
```

**Målvärde**: ≥ 0.7 (70% av relevanta chunks i top-5)

---

### 3. Context Recall (Kontexttäckning)

**Vad**: Mäter om alla relevanta chunks hittades.

**Hur**:
1. Jämför hittade chunks med ground truth
2. Score = relevant_retrieved / total_relevant

**Exempel**:
```
Ground truth nämner: RF 2 kap. 1 §, RF 2 kap. 2 §
Hittade: RF 2 kap. 1 §
→ Recall: 0.5 (50% av relevanta chunks hittade)
```

**Målvärde**: ≥ 0.6 (60% av relevanta chunks hittade)

---

### 4. Answer Relevancy (Svarsrelevans)

**Vad**: Mäter om svaret är relevant för frågan.

**Hur**:
1. Semantic similarity mellan fråga och svar
2. Kontrollera att svaret faktiskt besvarar frågan

**Exempel**:
```
Fråga: "Hur överklagar jag ett beslut?"
Svar: "Beslut överklagas genom förvaltningsbesvär..."
→ Relevancy: 0.9 (direkt svar på frågan)
```

**Målvärde**: ≥ 0.8 (80% relevans)

---

## Golden Set

### Struktur

55 frågor fördelade på 7 kategorier:

| Kategori | Antal | Beskrivning |
|----------|-------|-------------|
| **SFS_PRIMARY** | 8 | Kräver exakt §-citat från lagtext |
| **PRAXIS** | 6 | Myndighetspraktik, kan vara sekundärkällor |
| **EDGE_CASES** | 4 | Förkortningar, felstavningar, förtydliganden |
| **SMALLTALK** | 2 | Ska INTE trigga RAG |
| **DIVA_FORSKNING** | 12 | Forskningsfrågor mot DiVA-akademiska källor |
| **KORSKOLLEKTION** | 8 | Kräver både lag + forskning (cross-collection) |
| **KOMMUN_JURIDIK** | 10 | Kommunallagen (2017:725): självstyre, nämnder, revision |
| **TEMPORALA_FRAGOR** | 5 | Lagändringar över tid, ikraftträdanden |

### Exempel-fråga

```json
{
  "id": "sfs_01",
  "query": "Vad säger Regeringsformen om yttrandefrihet?",
  "intent": "SFS_PRIMARY",
  "expected_sfs": "1974:152",
  "expected_ref": "RF 2 kap. 1 §",
  "ground_truth": "Var och en är gentemot det allmänna tillförsäkrad yttrandefrihet...",
  "evidence_level": "green",
  "should_search": true
}
```

---

## Körning

### Quick Test (2 min)

```bash
constitutional eval --quick
```

- 10 frågor
- RAGAS-mått
- Sparar resultat till `eval/results/`

### Full Test (10 min)

```bash
constitutional eval --full
```

- 55 frågor (alla kategorier)
- Komplett RAGAS-analys
- Jämförelse per intent-kategori

### Lightweight (utan RAGAS)

```bash
constitutional eval --quick --provider lightweight
```

- Använder heuristiker istället för LLM
- Snabbare (30s)
- Lägre precision

---

## Output

### Console

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Constitutional-AI Evaluation Report
Version: 1.0-P0 | 2025-12-21T16:30:00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Questions: 20 | Pass: 18 | Fail: 2 | Pass Rate: 90.0%

RAGAS Scores
┌─────────────────────┬─────────┐
│ Metric              │   Score │
├─────────────────────┼─────────┤
│ Faithfulness        │   0.870 │
│ Context Precision   │   0.820 │
│ Context Recall      │   0.790 │
│ Answer Relevancy    │   0.910 │
└─────────────────────┴─────────┘

Results by Intent
┌──────────────────┬───────┬────────┬────────┬───────────┐
│ Intent           │ Total │ Passed │ Failed │ Pass Rate │
├──────────────────┼───────┼────────┼────────┼───────────┤
│ SFS_PRIMARY      │     8 │      7 │      1 │       88% │
│ PRAXIS           │     6 │      6 │      0 │      100% │
│ EDGE_CASES       │     4 │      4 │      0 │      100% │
│ SMALLTALK        │     2 │      1 │      1 │       50% │
└──────────────────┴───────┴────────┴────────┴───────────┘

Failed Questions:
  • sfs_07: Hur lång tid har en myndighet på sig...
    Evidence: yellow, Faithfulness: 0.65
  • small_02: Vad är klockan?
    Error: Triggered RAG when it shouldn't
```

### JSON

```json
{
  "timestamp": "2025-12-21T16:30:00",
  "version": "1.0-P0",
  "total_questions": 20,
  "passed": 18,
  "failed": 2,
  "pass_rate": 0.9,
  "avg_faithfulness": 0.87,
  "avg_context_precision": 0.82,
  "avg_context_recall": 0.79,
  "avg_answer_relevancy": 0.91,
  "by_intent": {
    "SFS_PRIMARY": {"total": 8, "passed": 7, "failed": 1},
    "PRAXIS": {"total": 6, "passed": 6, "failed": 0},
    "EDGE_CASES": {"total": 4, "passed": 4, "failed": 0},
    "SMALLTALK": {"total": 2, "passed": 1, "failed": 1}
  },
  "results": [...]
}
```

---

## Pass/Fail Kriterier

### SFS_PRIMARY

- **Pass**: evidence_level == "green" AND faithfulness ≥ 0.7
- **Fail**: Annars

### PRAXIS

- **Pass**: evidence_level in ["green", "yellow"] AND faithfulness ≥ 0.6
- **Fail**: Annars

### EDGE_CASES

- **Pass**: sources_count > 0 AND faithfulness ≥ 0.5
- **Fail**: Annars

### SMALLTALK

- **Pass**: sources_count == 0 (ska INTE trigga RAG)
- **Fail**: Annars

---

## Jämförelse med Baseline

```bash
constitutional eval --full --compare baseline_2025-12-21.json
```

Output:
```
Comparison with baseline_2025-12-21.json

Faithfulness:       0.87 (↑ 0.03 from baseline)
Context Precision:  0.82 (↓ 0.01)
Context Recall:     0.79 (→ same)
Answer Relevancy:   0.91 (↑ 0.05)

⚠️  Regressions detected:
  - legal_07: context_precision dropped 0.15
  - def_03: faithfulness dropped 0.20
```

---

## Continuous Integration

### GitHub Actions (framtida)

```yaml
name: RAG Evaluation

on: [push, pull_request]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run evaluation
        run: |
          constitutional eval --quick --provider lightweight
      - name: Check pass rate
        run: |
          # Fail if pass rate < 80%
          python check_pass_rate.py
```

---

## Troubleshooting

### RAGAS inte installerad

```bash
pip install ragas datasets
```

### Timeout

```bash
# Öka timeout i eval_runner.py
TIMEOUT = 120.0  # sekunder
```

### Backend inte tillgänglig

```bash
# Kolla att backend körs
curl http://localhost:8000/api/constitutional/health

# Starta om om nödvändigt
systemctl --user restart constitutional-ai-backend
```

---

## Roadmap

### P0 (Klart)
- [x] Golden set (20 frågor)
- [x] RAGAS-integration
- [x] CLI-kommando
- [x] Console output

### P1 (Klart)
- [x] Utöka till 55 frågor (DiVA, cross-collection, kommun, temporal)
- [x] Retrieval quality evaluation suite
- [x] Chunk quality analysis
- [ ] Baseline-jämförelse (automatiserad)
- [ ] Regression detection
- [ ] CI/CD-integration

### P2 (Framtida)
- [ ] Lightweight metrics (utan LLM)
- [ ] Per-model comparison
- [ ] A/B testing framework
- [ ] Automated retraining triggers
