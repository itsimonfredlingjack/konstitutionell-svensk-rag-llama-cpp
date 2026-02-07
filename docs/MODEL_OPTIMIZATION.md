# Modelloptimering - Constitutional AI

> Dokumentation av modellparametrar, system prompts och best practices för prompt engineering

**Senast uppdaterad:** 2025-12-15

---

## Översikt

Constitutional AI använder llama-server (llama.cpp) med lokala modeller för att svara på frågor baserat på en korpus med över 521 000 svenska myndighetsdokument.

### Modeller

- **Primär modell:** `ministral-3:14b` (Mistral AI) - GGUF format via llama-server
- **Fallback modell:** `gpt-sw3:6.7b` (AI Sweden GPT-SW3) - GGUF format via llama-server
- **Timeout:** 60 sekunder (fallback vid timeout)

---

## Modellparametrar

### Per Response Mode

#### EVIDENCE Mode (Juridisk expert, formell)
```python
{
    "temperature": 0.2,      # Mycket låg - fokuserat och exakt
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 1024      # Längre svar för detaljerade citationer
}
```

**Användning:** När användaren ber om specifika lagreferenser eller formella svar med citationer.

#### ASSIST Mode (Hjälpsam assistent, balanserad)
```python
{
    "temperature": 0.4,      # Låg-mellan - balanserat
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 1024      # Längre svar för detaljerade förklaringar
}
```

**Användning:** Standardläge för de flesta juridiska frågor. Balanserar exakthet med läsbarhet.

#### CHAT Mode (Smalltalk, avslappnad)
```python
{
    "temperature": 0.7,      # Högre - mer kreativt och varierat
    "top_p": 0.9,            # Fokuserad sampling
    "repeat_penalty": 1.1,   # Undviker repetitioner
    "num_predict": 512       # Kortare svar för smalltalk
}
```

**Användning:** För hälsningar, meta-frågor och smalltalk som inte kräver RAG.

---

## System Prompts

### ASSIST Mode Prompt

```
Du är Constitutional AI, en expert på svensk lag och myndighetsförvaltning.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling)
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT:
1. Använd ALLTID källorna som tillhandahålls i kontexten när de finns
2. Citera källor i formatet [Källa X] när du refererar till dem
3. Prioritera SFS-källor (lagtext) över prop/sou när båda finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information
5. Var kortfattat men exakt - MAX 150 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Inga rubriker, inga punktlistor, inga asterisker
8. Gå rakt på sak och var hjälpsam
```

**Fil:** `09_CONSTITUTIONAL-AI/backend/app/services/orchestrator_service.py` (rad ~572-598)

### EVIDENCE Mode Prompt

```
Du är en juridisk expert specialiserad på svensk lag och förvaltningsrätt.

KUNSKAPSBAS:
Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument från ChromaDB, inklusive:
- SFS-lagtext (Svensk författningssamling) - PRIORITERA DETTA
- Propositioner från Riksdagen
- SOU-rapporter (Statens offentliga utredningar)
- Motioner, betänkanden och andra riksdagsdokument

ARBETSSÄTT FÖR EVIDENCE-MODE:
1. Använd ENDAST källor från korpusen - hitta på ingenting
2. Citera ALLTID exakta SFS-nummer och paragrafer när de finns i källorna
3. PRIORITERA SFS-källor (lagtext) över prop/sou/bet när flera källor finns
4. Om källor saknas eller är lågkvalitativa, säg tydligt: "Jag saknar specifik information i korpusen"
5. Var formell, exakt och saklig - MAX 200 ord
6. INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering
7. Citera källor med [Källa X] och inkludera SFS-nummer/paragraf när tillgängligt
```

**Fil:** `09_CONSTITUTIONAL-AI/backend/app/services/orchestrator_service.py` (rad ~600-621)

### CHAT Mode Prompt

```
Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat.
```

**Fil:** `09_CONSTITUTIONAL-AI/backend/app/services/orchestrator_service.py` (rad ~623-627)

---

## User Prompt Struktur

### ASSIST/EVIDENCE Mode User Prompt

```
Fråga: {question}

Källor från korpusen:
{Källa 1: titel} ⭐ PRIORITET (SFS) | Relevans: 0.85
{full_text}

{Källa 2: titel} Typ: PROP | Relevans: 0.72
{full_text}

...

Instruktioner:
- Använd källorna ovan för att svara på frågan
- Citera källor med [Källa X] när du refererar till dem
- Om källor saknas, säg tydligt att du saknar specifik information
- Prioritera SFS-källor (lagtext) om flera källor finns

Svara i ren text utan formatering.
```

**Viktiga detaljer:**
- Källor formateras med doc_type och score
- SFS-källor markeras med ⭐ PRIORITET
- Instruktioner om källanvändning ingår explicit

---

## Best Practices för Prompt Engineering

### 1. Referera till korpusen

**BRA:**
- "Du har tillgång till en korpus med över 521 000 svenska myndighetsdokument"
- "Använd källorna från korpusen när de finns"

**DÅLIGT:**
- "Svara på frågan" (ingen referens till korpusen)
- Generiska prompts utan kontext

### 2. Instruera om källanvändning

**BRA:**
- "Använd ALLTID källorna som tillhandahålls i kontexten när de finns"
- "Citera källor i formatet [Källa X] när du refererar till dem"

**DÅLIGT:**
- Ingen instruktion om hur källor ska användas
- Antagande att modellen automatiskt använder källor

### 3. Hantera saknade källor

**BRA:**
- "Om källor saknas eller är lågkvalitativa, säg tydligt att du saknar specifik information"
- "Jag saknar specifik information i korpusen"

**DÅLIGT:**
- Ingen instruktion om vad man ska göra när källor saknas
- Modellen hittar på svar när källor saknas

### 4. Prioritera källor

**BRA:**
- "Prioritera SFS-källor (lagtext) över prop/sou när båda finns"
- "PRIORITERA SFS-källor (lagtext) över prop/sou/bet"

**DÅLIGT:**
- Ingen instruktion om källprioritering
- Alla källor behandlas lika

### 5. Var tydlig om format

**BRA:**
- "INGEN MARKDOWN - skriv ren text utan *, **, #, - eller formatering"
- "Citera källor med [Källa X]"

**DÅLIGT:**
- Otydliga instruktioner om format
- Antagande att modellen vet formatet

---

## Testning av Modelloptimeringar

### Testfrågor per Mode

#### ASSIST Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Vad säger GDPR om personuppgifter?",
    "mode": "assist"
  }' | jq .
```

**Förväntat:**
- Svar baserat på källor från korpusen
- Citationer med [Källa X]
- Prioritering av SFS-källor om de finns
- Max 150 ord

#### EVIDENCE Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Vad säger förvaltningslagen 2017:900 om beslut?",
    "mode": "evidence"
  }' | jq .
```

**Förväntat:**
- Exakta SFS-nummer och paragrafer
- Formellt språk
- Prioritering av SFS-källor
- Max 200 ord

#### CHAT Mode
```bash
curl -X POST http://localhost:8900/api/constitutional/agent/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Hej, vad kan du hjälpa mig med?",
    "mode": "chat"
  }' | jq .
```

**Förväntat:**
- Kortfattat svar (2-3 meningar)
- Avslappnad ton
- Eventuell hänvisning till korpusen om relevant

### Verifiering

**Kontrollera att:**
1. Modellen använder källor när de finns
2. Citationer ingår i formatet [Källa X]
3. SFS-källor prioriteras när flera källor finns
4. Modellen säger tydligt när källor saknas
5. Formatet är ren text utan markdown

---

## Ändringshistorik

### 2025-12-15 - Första optimering
- Förbättrade system prompts med referenser till korpusen
- Lade till top_p och repeat_penalty parametrar
- Ökade num_predict för ASSIST/EVIDENCE modes
- Förbättrade källformatering med doc_type och score
- Justerade temperature per mode (EVIDENCE: 0.2, ASSIST: 0.4, CHAT: 0.7)

---

## Referenser

- llama.cpp server API: https://github.com/ggerganov/llama.cpp/blob/master/examples/server/README.md
- Ollama (fallback/optional): https://github.com/ollama/ollama/blob/main/docs/api.md
- Mistral AI: https://mistral.ai/
- AI Sweden GPT-SW3: https://huggingface.co/fcole90/ai-sweden-gpt-sw3-6.7b
- ChromaDB: https://www.trychroma.com/
