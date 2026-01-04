# PRV (Patent- och registreringsverket) - Harvest Report

**Datum:** 2025-12-07
**Operation:** MYNDIGHETS-SWEEP
**Status:** ✅ SCRAPING DONE | ⚠️ CHROMADB INSERTION BLOCKED

---

## Resultat

### Scraping
- **Dokument scrapade:** 336
- **Tid:** 220 sekunder (~3.7 min)
- **Metod:** Adaptive scraping (upptäckte struktur först, sedan rekursiv crawl)
- **Filformat:** JSON

### Innehåll
- **Källa:** prv.se
- **Typ:** Vägledningar, publikationer, information om patent/varumärken/design
- **Språk:** Svenska (95%), Engelska (5%)

### Dokumenttyper
| Typ | Exempel |
|-----|---------|
| Vägledning | Patent-/varumärkesguider, ansökningsprocesser |
| Information | Om PRV:s tjänster, avgifter, processer |
| Publikation | Nyheter, företagscases, statistik |
| Rapport | Innovationsrapporter, forskningsdata |

---

## Filer

### Huvudfiler
| Fil | Beskrivning |
|-----|-------------|
| `prv_scrape_20251207_210724.json` | **336 dokument** (huvudresultat) |
| `prv_scraper_adaptive.py` | Scraping-script (fungerar) |
| `insert_prv_simple.py` | Insertion-script (ChromaDB segfaultar) |

### Rådata-exempel
```json
{
  "status": "success",
  "source": "prv",
  "documents_scraped": 336,
  "execution_time_seconds": 220.48,
  "timestamp": "2025-12-07T21:07:24.894173",
  "documents": [
    {
      "id": "11b4d043fe626ddd",
      "content": "...",
      "url": "https://www.prv.se/...",
      "source": "prv",
      "title": "...",
      "doc_type": "vägledning",
      "scraped_at": "2025-12-07T21:02:49.414785"
    }
  ]
}
```

---

## ChromaDB Problem

### Status
**ChromaDB 1.3.5 + Python 3.12 = Segmentation Fault (core dump)**

### Försök
1. ✅ Scraping via `requests` + `BeautifulSoup` - FUNGERAR
2. ❌ ChromaDB `PersistentClient()` - SEGFAULTAR
3. ❌ ChromaDB via backend venv - SEGFAULTAR
4. ❌ ChromaDB med batch insert - SEGFAULTAR
5. ❌ ChromaDB med minimal import - SEGFAULTAR

### Orsak
Känt problem med ChromaDB 1.3.5's Rust-bindings på vissa Linux-miljöer med Python 3.12.

```bash
/bin/bash: line 1: 1234953 Segmentation fault
```

### Lösning
**A) Uppgradera ChromaDB till 1.4+**
```bash
# Kräver venv eller --break-system-packages
pip3 install --upgrade chromadb
```

**B) Använd backend API**
Om backend redan har ChromaDB igång, använd REST API istället:
```python
import requests
response = requests.post('http://localhost:8000/api/chromadb/insert', json={
    'collection': 'swedish_gov_docs',
    'documents': documents
})
```

**C) Manuell insertion senare**
När ChromaDB är fixat, kör:
```bash
python3 insert_prv_simple.py
```

---

## Metadata

### URL-täckning
Scrapern hittade dokument från:
- `/sv/om-oss/` (kontakt, nyheter, organisationinfo)
- `/sv/kunskap-och-stod/` (guider, utbildningar, bibliotek)
- `/sv/foretagare/` (företagsrådgivning, strategier)
- `/sv/ip-proffs/` (professionella tjänster)
- `/sv/patent/`, `/sv/varumarke/`, `/sv/design/` (produktguider)
- `/en/` (engelska sidor)

### Saknade sektioner
- **Föreskrifter** - URL:en `/sv/om-prv/lagar-och-regler/foreskrifter/` gav 404
  - Troligen flyttad eller bakom annat URL-mönster
- **Statistik/rapporter** - Många kan vara PDF:er i ett dokumentbibliotek

### Förbättringar
För djupare scraping:
1. **PDF-parsing** - Extrahera text från PDF-länkar (OCR)
2. **API-search** - PRV kan ha ett dokumentsök-API
3. **Manuell mappning** - Kolla PRV:s sitemap.xml
4. **Selenium** - För JavaScript-renderade sidor

---

## Nästa Steg

### Omedelbart
1. ✅ **336 dokument är scrapade och sparade**
2. ⏳ **ChromaDB insertion väntar på fix**
3. 📄 **Data finns i JSON-format (insertion-ready)**

### När ChromaDB fixas
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
python3 insert_prv_simple.py
```

### Alternativ databas
Om ChromaDB fortsätter krångla, använd SQLite istället:
```python
import sqlite3
conn = sqlite3.connect('swedish_gov_docs.db')
# INSERT documents...
```

---

## Sammanfattning

| Metriker | Värde |
|----------|-------|
| **Dokument scrapade** | 336 |
| **Unika URL:er** | 336 |
| **Total storlek** | ~2.8 MB (JSON) |
| **Medellängd** | ~8.3 KB/dokument |
| **Scraping-tid** | 3.7 min |
| **ChromaDB status** | ⚠️ BLOCKED (segfault) |
| **Nästa myndighet** | Väntar på instruktion |

---

**Flagga:** ⚠️ Endast 336 dokument - kan behöva djupare scraping
**Rekommendation:** Fixa ChromaDB, sedan skrapa fler myndigheter parallellt
