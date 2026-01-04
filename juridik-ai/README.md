# juridik-ai

En kraftfull CLI-tool för analys av svenska myndighetsdokument med lokala AI-modeller.

**Din lokala assistent för hela myndighetssverige** - analysera beslut, dokument och administrativa handlingar med Qwen 2.5 3B direkt på din dator utan molnberoenden.

## Funktioner

- **analyze** - Analysera myndighetsbeslut och dokument med djup juridisk granskning
- **fraga** - Ställ frågor om svenska myndigheter, rättigheter och förvaltningsrätt
- **quick** - Få snabba svar på juridiska frågor (fallback-modell)
- **batch** - Batch-analysera hela dokumentkataloger automatiskt
- **split** - Dela upp långa dokument för effektivare analys
- **models** - Lista installerade AI-modeller
- **status** - Visa GPU-status och Ollama-systeminfo

## Installation

### Krav

- **Python 3.8+** (rekommenderas Python 3.11+)
- **Ollama** - lokala AI-modeller (https://ollama.ai)
- **NVIDIA GPU** - rekommenderas för snabbare analys (RTX 2060 eller bättre)
- **curl** - för API-kommunikation

### Setup Fedora/Linux

```bash
# 1. Installera Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Klona juridik-ai
cd /home/dev
git clone <repo-url> juridik-ai
cd juridik-ai

# 3. Gör CLI-scriptet körbart
chmod +x juridik-ai

# 4. (Valfritt) Lägg till i PATH
sudo ln -s $(pwd)/juridik-ai /usr/local/bin/juridik-ai
```

### Första gången

```bash
# 1. Starta Ollama
ollama serve

# 2. I ett annat terminal-fönster: Ladda ned och installera modeller
ollama pull qwen2.5:3b-instruct
ollama pull llama3.2:3b-instruct
ollama pull gemma2:2b

# 3. Skapa custom modeller för juridisk analys
cd /path/to/juridik-ai
ollama create qwen-myndighet -f Modelfile.qwen-myndighet
ollama create qwen-juridik -f Modelfile.qwen-juridik

# 4. Verifiera installation
./juridik-ai models
```

## Snabbstart

```bash
# 1. Analysera ett myndighetsbeslut
./juridik-ai analyze mitt_arende.txt

# 2. Ställ en myndighetsfråga
./juridik-ai fraga "Hur överklagar jag Försäkringskassans beslut?"

# 3. Få ett snabbt svar
./juridik-ai quick "Vad innebär serviceskyldigheten?"

# 4. Se GPU-status
./juridik-ai status

# 5. Batch-analysera en mapp med dokument
./juridik-ai batch ./dokument --task loggbok
```

## Kommandoreferens

### analyze - Analysera myndighetsdokument

Analyserar ett dokument enligt myndighetsloggbok-format med strukturerad juridisk bedömning.

```bash
./juridik-ai analyze <dokument> [--model <modell>]
```

**Argument:**
- `<dokument>` - Sökväg till dokument (TXT, PDF text, etc.)
- `--model` - Modell att använda (default: `qwen`). Alternativ: `qwen`, `qwen-juridik`, `qwen-base`

**Exempel:**

```bash
# Analysera ett JO-beslut
./juridik-ai analyze jo-beslut-2024.txt

# Analysera med juridik-specialiserad modell
./juridik-ai analyze socialtjanst-arende.txt --model qwen-juridik
```

**Output:**
Genererar strukturerad analys med:
- Berörda myndigheter
- Tillämpliga lagar och paragrafer
- Identifierade problem (med allvarlighetsgrad)
- Dina rättigheter enligt förvaltningslagen
- Rekommenderade åtgärder
- Kontaktvägar för klagomål

Resultatet sparas automatiskt i `output/` katalogen.

### fraga - Ställ myndighetsfrågor

Besvara strukturerade frågor om svenska myndigheter, rättigheter och förvaltningsrätt.

```bash
./juridik-ai fraga "<din fråga>" [--model <modell>]
```

**Argument:**
- `<fråga>` - Din fråga (använd citationstecken)
- `--model` - Modell att använda (default: `qwen`)

**Exempel:**

```bash
# Fråga om överklagande
./juridik-ai fraga "Hur överklagar jag ett myndighetsbeslut?"

# Fråga om rättigheter
./juridik-ai fraga "Vad är offentlighetsprincipen och hur använder jag den?"

# Fråga om en specifik myndighet
./juridik-ai fraga "Vilka beslut fattar Arbetsförmedlingen och hur överklagar man?"

# Använd juridik-specialmodell
./juridik-ai fraga "Vad är förvaltningsprocessen?" --model qwen-juridik
```

**Svar innehåller:**
- Relevant myndighet eller instans
- Tillämpliga lagar och regler
- Praktisk vägledning steg-för-steg
- Kontaktvägar och nästa steg

### quick - Snabbt svar

Få snabba svar på juridiska frågor. Använder Llama 3.2 som fallback om Qwen inte är tillgänglig.

```bash
./juridik-ai quick "<fråga>"
```

**Exempel:**

```bash
./juridik-ai quick "Vad är § 20 förvaltningslagen?"
./juridik-ai quick "Hur lång är överklagandetiden?"
./juridik-ai quick "Vad gäller sekretesslagen?"
```

### batch - Batch-analysera dokument

Analysera flera dokument i en katalog automatiskt.

```bash
./juridik-ai batch <katalog> [--task <typ>] [--output <output-katalog>]
```

**Argument:**
- `<katalog>` - Sökväg till mapp med dokument
- `--task, -t` - Analystyp (default: `loggbok`)
  - `loggbok` - Myndighetsloggbok-analys
  - `risk` - Riskanalys
  - `sammanfatta` - Sammanfattning
  - `brister` - Identifiera brister
- `--output, -o` - Output-katalog (default: `output/batch`)

**Exempel:**

```bash
# Analysera alla dokument i en mapp
./juridik-ai batch ./mina-arenden

# Batch-risk-analys
./juridik-ai batch ./dokument --task risk --output ./riskanalyser

# Batch-sammanfattning
./juridik-ai batch ./beslut --task sammanfatta
```

### split - Dela upp långa dokument

Delar upp långa dokument i mindre, hanterliga sektioner för effektivare analys.

```bash
./juridik-ai split <dokument> [--output <output-katalog>]
```

**Argument:**
- `<dokument>` - Sökväg till långt dokument
- `--output, -o` - Output-katalog (default: `output/sections/<dokumentnamn>`)

**Exempel:**

```bash
# Dela upp en lång utredning
./juridik-ai split utredning-2024.txt

# Spara sektioner på annan plats
./juridik-ai split stort-arende.txt --output ./mina-sektioner

# Efter split: analysera sektioner
./juridik-ai batch ./mina-sektioner --task loggbok
```

### models - Lista installerade modeller

Visa vilka AI-modeller som är installerade och vilka juridik-AI använder.

```bash
./juridik-ai models
```

**Output:**
- Lista av alla installerade modeller i Ollama
- Status för juridik-AI:s modeller (installerad/saknas)

**Exempel:**

```bash
$ ./juridik-ai models
📦 Installerade modeller:

NAME                        ID              SIZE    MODIFIED
qwen2.5:3b-instruct        abc1234...      2.2 GB  2 hours ago
qwen-myndighet             def5678...      2.2 GB  2 hours ago
llama3.2:3b-instruct       ghi9012...      2.0 GB  1 day ago

🎯 Juridik-AI modeller:
  ✅ qwen: qwen-myndighet
  ✅ qwen-juridik: qwen-juridik
  ✅ qwen-base: qwen2.5:3b-instruct
  ✅ llama: llama3.2:3b-instruct
  ❌ gemma: gemma2:2b
```

### status - GPU och Ollama-status

Visa GPU-resursanvändning och Ollama-systemstatus.

```bash
./juridik-ai status
```

**Output:**
- GPU-namn och VRAM-användning
- GPU-temperatur
- GPU-belastning
- Vilka modeller som är inladdade i Ollama

**Exempel:**

```bash
$ ./juridik-ai status
🖥️ GPU-status:

  GPU: NVIDIA GeForce RTX 2060
  VRAM: 4200 MB / 6144 MB
  Temp: 52°C
  Load: 85%

🤖 Ollama-status:
  NAME                    ID              SIZE    UNTIL
  qwen-myndighet          abc1234...      2.2 GB  4 minutes from now
```

## AI-Modeller

Projektet använder custom-modeller baserade på Qwen 2.5 3B, optimerade för svensk juridik och förvaltningsrätt.

### qwen-myndighet (Rekommenderad)

Primär modell för analys av myndighetsbeslut och administrativa handlingar.

**Specialisering:**
- Hela myndighetssverige (Försäkringskassan, Skatteverket, AF, Migrationsverket, etc.)
- Förvaltningslagen och administrativ rätt
- Kommuner och regioner
- Offentlighetsprincipen
- Tillsynsmyndigheter (JO, IVO, Skolinspektionen, etc.)

**Konfiguration:**
- Temperatur: 0.3 (låg för konsistenta, sakliga svar)
- Context-längd: 4096 tokens
- Optimerad för RTX 2060 (6GB VRAM)

**Använd för:**
```bash
./juridik-ai analyze dokument.txt
./juridik-ai fraga "Din fråga här"
./juridik-ai batch ./dokument
```

### qwen-juridik

Specialiserad modell för juridisk analys och förvaltningsprocesser.

**Specialisering:**
- Förvaltningsrätt och förvaltningslagen
- JO-beslut och JO:s tillsynspraxis
- Riksdagens lagstiftningsprocess
- Offentlighetsprincipen och sekretess
- Socialtjänst och LSS

**Använd för:**
```bash
./juridik-ai analyze komplext-arende.txt --model qwen-juridik
./juridik-ai fraga "Förklara förvaltningsprocessen" --model qwen-juridik
```

### Fallback-modeller

För snabbfrågor och alla-kan-svar finns fallback-modeller:

- **qwen2.5:3b-instruct** - Generell Qwen-modell (snabbt svar)
- **llama3.2:3b-instruct** - Llama 3.2 (används för `quick`)
- **gemma2:2b** - Google Gemma 2 (lätt modell)

## Projektstruktur

```
juridik-ai/
├── juridik-ai                      # Huvudprogram (Python CLI)
├── README.md                       # Denna fil
├── Modelfile.qwen-myndighet        # Custom Ollama-modell (myndigheter)
├── Modelfile.qwen-juridik          # Custom Ollama-modell (juridik)
├── workflows/                      # Python-moduler för processering
│   ├── long_document_split.py      # Dokumentuppdelning
│   ├── qwen_batch_analyze.py       # Batch-analys
│   └── output_formatter.py         # Formatering av svar
├── system-prompts/                 # System prompts för modellerna
│   ├── qwen-myndighet.txt          # Prompt för myndighets-modell
│   ├── qwen-juridik.txt            # Prompt för juridik-modell
│   ├── llama-general.txt           # Prompt för Llama
│   └── gemma-light.txt             # Prompt för Gemma
├── templates/                      # Outputmallar
│   ├── myndighetsloggbok-template.md
│   ├── riskanalys-template.md
│   ├── loggbok-template.md
│   └── dokumentanalys-template.md
├── examples/                       # Exempeldokument
├── output/                         # Genererade analyser
└── data/                          # Datakatalog
```

## Typiska användningsfall

### 1. Analysera ett myndighetsbeslut

Du har mottagit ett myndighetsbeslut och vill förstå om det är felaktigt:

```bash
./juridik-ai analyze jo-besvar.txt
```

Får du en långt och detaljerat dokument:

```bash
./juridik-ai split utredning.txt
./juridik-ai batch ./utredning/sections --task loggbok
```

### 2. Förstå dina rättigheter

Du vill veta hur du överklagar ett beslut:

```bash
./juridik-ai fraga "Hur överklagar jag ett myndighetsbeslut hos Försäkringskassan?"
```

Eller snabbt svar:

```bash
./juridik-ai quick "Vilken är överklagandetiden för motsägelse?"
```

### 3. Riskanalys av flera ärenden

Du har flera dokument och vill göra en riskanalys på alla:

```bash
./juridik-ai batch ./mina-arenden --task risk --output ./riskanalyser
```

### 4. Batch-process hela kataloger

Procesera alla dokument i en mapp automatiskt:

```bash
./juridik-ai batch ./dokument --task sammanfatta
```

## Konfiguration

### Modelvalg

Ändra standardmodell i `juridik-ai`-scriptet:

```python
MODELS = {
    "qwen": "qwen-myndighet",        # Primär modell
    "qwen-juridik": "qwen-juridik",  # Juridik-specialiserad
    "qwen-base": "qwen2.5:3b-instruct",
    "llama": "llama3.2:3b-instruct",
    "gemma": "gemma2:2b"
}
```

### Ollama-inställningar

Anpassa GPU-användning i Modelfile:

```dockerfile
PARAMETER num_gpu 999          # GPU-layers
PARAMETER temperature 0.3      # Kreativitet (låg = saklig)
PARAMETER num_ctx 4096         # Context-längd
```

### Output-katalog

Standard output sparas i `output/`. Ändra genom att redigera:

```python
OUTPUT_DIR = BASE_DIR / "output"
```

## Felsökning

### Problem: "Kunde inte ansluta till Ollama"

```bash
# Starta Ollama
ollama serve

# Eller kontrollera att den redan kör
ollama ps
```

### Problem: "Modellen finns inte"

```bash
# Lista installerade modeller
./juridik-ai models

# Installera saknade modeller
ollama pull qwen2.5:3b-instruct
ollama pull llama3.2:3b-instruct
ollama pull gemma2:2b

# Skapa custom modeller
ollama create qwen-myndighet -f Modelfile.qwen-myndighet
ollama create qwen-juridik -f Modelfile.qwen-juridik
```

### Problem: GPU-acceleration fungerar inte

```bash
# Kontrollera GPU-status
./juridik-ai status

# Verifiera NVIDIA-driver
nvidia-smi

# CUDA måste vara installerad
nvcc --version
```

### Problem: Långsamt svar

1. Kontrollera GPU-användning: `./juridik-ai status`
2. Minska context-längd i Modelfile (`num_ctx`)
3. Använd mindre modell (Gemma 2B istället för Qwen 3B)
4. Stäng andra program som använder GPU

## System-prompts

Varje modell använder en specialutformad system prompt för att ge bättre juridiska svar. Dessa finns i `system-prompts/` och kan anpassas:

- **qwen-myndighet.txt** - Instruktioner för myndighetsanalys
- **qwen-juridik.txt** - Instruktioner för juridisk granskning
- **llama-general.txt** - Generell instruktion
- **gemma-light.txt** - Lätt instruktion för snabbsvar

Redigera dessa filer för att anpassa modellernas beteende.

## Juridisk ansvarsfriskrivning

juridik-ai är ett verktyg för **informationsändamål** och **stöd vid granskning av dokument**. Det är **inte** en ersättning för rättslig rådgivning från en advokat eller juridisk expert.

- Använd verktyget för att bättre förstå myndighetsbeslut
- Kontrollera alltid information från officiella myndighetskällor
- Vid viktiga rättsliga frågor, rådgör med en juridisk expert
- Författaren ansvarar inte för felaktiga tolkningar eller juridiska konsekvenser

## Licens

MIT License - Se LICENSE-fil för detaljer.

Du är fri att:
- Använda verktyget privat och kommersiellt
- Modifiera och distribuera kopior
- Använda för privat och öppen källkods-projekt

Under villkoret att:
- Du inkluderar licensen och copyright-notering
- Du inte ger garantier för verktyget

## Bidrag

Bidrag är välkomna! Föreslå förbättringar genom:

1. Fork repositoriet
2. Skapa en feature-branch (`git checkout -b feature/ny-funktion`)
3. Commit dina ändringar (`git commit -m 'Lägg till ny-funktion'`)
4. Push till branch (`git push origin feature/ny-funktion`)
5. Öppna en Pull Request

## Support och feedback

- Rapportera fel som Issues
- Föreslå nya funktioner
- Dela erfarenheter och användningsfall
- Förbättra dokumentationen

## Relaterade resurser

- [Förvaltningslagen (2017:900)](https://www.riksdagen.se)
- [Justitieombudsmannen (JO)](https://www.jo.se)
- [Offentlighetsprincipen](https://www.riksdagen.se)
- [Ollama](https://ollama.ai)
- [Qwen modeller](https://huggingface.co/Qwen)

---

**Versionen:** 1.0.0
**Senast uppdaterad:** 2025-11-27
**Status:** Stabilt för privat/lokal användning
