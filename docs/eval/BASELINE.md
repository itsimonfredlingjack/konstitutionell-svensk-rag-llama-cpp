# Baseline Setup

## Steg 1: Installera RAGAS

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
source venv/bin/activate
pip install ragas datasets
```

## Steg 2: Kör baseline eval

```bash
constitutional eval --quick --output eval/results/baseline_2025-12-21.json
```

Detta kommer:
- Köra 10 frågor från golden set
- Mäta RAGAS-mått (faithfulness, context precision, context recall, answer relevancy)
- Spara resultat till `eval/results/baseline_2025-12-21.json`

## Steg 3: Verifiera baseline

```bash
cat eval/results/baseline_2025-12-21.json | jq '.avg_faithfulness, .avg_context_precision, .avg_context_recall, .avg_answer_relevancy'
```

Förväntat output (ungefär):
```
0.65  # faithfulness (innan tuning)
0.55  # context_precision (innan tuning)
0.50  # context_recall (innan tuning)
0.70  # answer_relevancy (innan tuning)
```

## Steg 4: Spara som referens

```bash
cp eval/results/baseline_2025-12-21.json eval/results/baseline_BEFORE_TUNING.json
```

Nu har du en baseline att jämföra mot efter varje tuning-steg!

## Nästa steg

Efter varje implementation (stabila IDs, snippet-rensning, etc.):

```bash
# Kör eval igen
constitutional eval --quick

# Jämför med baseline
constitutional eval --quick --compare eval/results/baseline_BEFORE_TUNING.json
```

Målet är att se:
- **Context Precision** ↑ (mindre brus högre upp)
- **Context Recall** ↑ (rätt lagrum hämtas)
- **Faithfulness** ↑ (svar håller sig till källor)
