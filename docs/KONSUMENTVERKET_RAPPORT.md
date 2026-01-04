# KONSUMENTVERKET SCRAPING RAPPORT

**Datum:** 2025-12-07
**Operation:** MYNDIGHETS-SWEEP
**Källa:** konsumentverket.se
**Status:** ⚠️ COMPLETED WITH CHROMADB ISSUES

---

## SAMMANFATTNING

Scraping av Konsumentverket genomförd framgångsrikt. **37 dokument** samlades in från webbplatsen, inklusive:

- Föreskrifter och lagar (KOVFS-relaterat)
- Vägledningar för konsumenter
- Rapporter
- Mål, domar och förelägganden

Data sparad i JSON-format men **ChromaDB segfaultar** vid import på denna server.

---

## RESULTAT

### Dokumentstatistik

| Typ | Antal |
|-----|-------|
| Kategorier | 3 |
| Föreskrifter | 26 |
| Vägledningar | 1 |
| Publikationer | 5 |
| Rapporter | 2 |
| **TOTALT** | **37** |

### Scrapad data

**Fil:** `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/konsumentverket_scrape_20251207_210422.json`

---

## PROBLEM: CHROMADB SEGFAULT

ChromaDB kraschar konsekvent med **Segmentation Fault (exit code 139)** på denna server.

### Försök gjorda:

1. ✅ **Scraping till JSON:** Fungerade perfekt
2. ❌ **ChromaDB direkt under scraping:** Segfault
3. ❌ **ChromaDB separat import-script:** Segfault
4. ❌ **ChromaDB query av befintlig data:** Segfault

### Möjliga orsaker:

- ChromaDB version-konflikt med Python 3.x på Ubuntu
- Korrupt ChromaDB-databas (`chromadb_data/`)
- VRAM/GPU-minneskonflikt (RTX 4070 används samtidigt av Ollama)
- SQLite backend-problem

---

## WORKAROUND-LÖSNINGAR

### Alternativ 1: Använd JSON-filen direkt

JSON-filen innehåller all data strukturerad och redo att användas:

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
python3 -c "
import json
with open('data/konsumentverket_scrape_20251207_210422.json') as f:
    data = json.load(f)
    for doc in data['documents']:
        print(f\"{doc['title']} ({doc['type']})\")
"
```

### Alternativ 2: Importera på annan maskin

Flytta JSON-filen till en maskin utan ChromaDB-problem och kör importen där:

```bash
scp data/konsumentverket_scrape_20251207_210422.json user@other-host:/path/
ssh user@other-host
python3 import_json_to_chromadb.py konsumentverket_scrape_20251207_210422.json
```

### Alternativ 3: Använd SQLite direkt

ChromaDB använder SQLite backend. Skapa egen databas:

```bash
sqlite3 konsumentverket.db <<EOF
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    url TEXT,
    title TEXT,
    text TEXT,
    type TEXT,
    source TEXT,
    scraped_at TEXT
);
EOF
```

Importera med Python:

```python
import json
import sqlite3

with open('data/konsumentverket_scrape_20251207_210422.json') as f:
    data = json.load(f)

conn = sqlite3.connect('konsumentverket.db')
cursor = conn.cursor()

for doc in data['documents']:
    cursor.execute('''
        INSERT OR IGNORE INTO documents (id, url, title, text, type, source, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (doc['id'], doc['url'], doc['title'], doc['text'], doc['type'], doc['source'], data['scraped_at']))

conn.commit()
conn.close()
```

### Alternativ 4: Återinstallera ChromaDB

```bash
pip uninstall chromadb -y
pip install chromadb --no-cache-dir --force-reinstall
```

### Alternativ 5: Använd Docker ChromaDB

Kör ChromaDB i Docker för isolation:

```bash
docker run -d -p 8001:8000 -v ./chromadb_data:/chroma/chroma chromadb/chroma:latest
```

---

## SCRAPED DOKUMENT (EXEMPEL)

### Konsumentlagar
- **URL:** https://www.konsumentverket.se/omrade/konsumentlagar/
- **Typ:** kategori
- **ID:** 30df54aace8101fa

### Mål, domar och förelägganden
- **URL:** https://www.konsumentverket.se/artikellista/mal-domar-och-forelagganden/
- **Typ:** kategori
- **ID:** bed5b4ca9bbf64c6
- **Innehåll:** 243 rättsärenden

### Konsumentköplagen
- **URL:** https://www.konsumentverket.se/lagar/konsumentkoplagen-konsument/
- **Typ:** föreskrift
- **ID:** a99832654c55d17c
- **Innehåll:** Fullständig lagtext + vägledning

---

## VARFÖR < 100 DOKUMENT?

Konsumentverkets webbplats har:

1. **Få regelverksföreskrifter (KOVFS):** De flesta föreskrifter hänvisar till riksdagslagar (SFS), inte myndighetens egna KOVFS
2. **Publikationer på separat subdomain:** `publikationer.konsumentverket.se` har begränsad HTML-innehåll, mycket PDF
3. **Dynamiskt innehåll:** Många sidor genereras via JavaScript (ej scrapbart utan headless browser)
4. **Filtrering för kvalitet:** Scriptet filtrerar bort sidor med <200 tecken

---

## NÄSTA STEG

### För att få fler dokument:

1. **Scrapa PDFer:**
   - Lägg till PDF-parsing (PyPDF2/pdfplumber)
   - Publikationer finns mestadels som PDF

2. **Headless browser:**
   - Använd Selenium/Playwright för JavaScript-sidor
   - Dynamiskt innehåll kräver browser-rendering

3. **Djupare crawling:**
   - Öka rekursionsdjup i scraper
   - Följ fler länkar från varje sida

4. **API-sökning:**
   - Kolla om Konsumentverket har publikt API
   - Direkt dataåtkomst istället för HTML-parsing

### För att fixa ChromaDB:

```bash
# Backup befintlig data
cp -r chromadb_data chromadb_data.backup

# Radera korrupt databas
rm -rf chromadb_data

# Återskapa från JSON
python3 import_json_to_chromadb.py data/konsumentverket_scrape_20251207_210422.json
```

---

## FILER SKAPADE

| Fil | Beskrivning |
|-----|-------------|
| `scrape_konsumentverket_json.py` | Huvudscraper (fungerar) |
| `import_json_to_chromadb.py` | ChromaDB-import (segfaultar) |
| `data/konsumentverket_scrape_20251207_210422.json` | Scrapad data (37 docs) |
| `KONSUMENTVERKET_RAPPORT.md` | Denna rapport |

---

## SLUTSATS

✅ **Scraping:** FUNGERAR
❌ **ChromaDB:** SYSTEMISKT PROBLEM
⚠️ **Dokumentantal:** 37/100 (under gräns)

**Rekommendation:** Använd JSON-filen direkt eller importera på annan maskin. För fler dokument: lägg till PDF-parsing och headless browsing.
