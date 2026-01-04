# Elsäkerhetsverket - Import Instructions

## Status

**✓ SCRAPING KLART:** 34 dokument harvested
**✗ CHROMADB IMPORT:** Blockerad av segfault (känt ChromaDB-problem)

---

## Data Location

**JSON Output:**
```
/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/elsak_harvest.json
```

**Innehåll:**
- 27 föreskrifter (ELSÄK-FS 2003-2022)
- 7 vägledningar
- 0 publikationer (inga hittades)
- 0 beslut (inga hittades)

---

## Import till ChromaDB (När segfault är fixad)

### Alternativ 1: Python Script
```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
python3 scrapers/elsak_import_to_chromadb.py
```

### Alternativ 2: Manuell Import
```python
import json
import chromadb

# Ladda data
with open('data/elsak_harvest.json') as f:
    data = json.load(f)

# Anslut till ChromaDB
client = chromadb.PersistentClient(path='chromadb_data')
collection = client.get_or_create_collection('swedish_gov_docs')

# Importera dokument
for idx, doc in enumerate(data['documents']):
    doc_id = f"elsak_{idx}"
    content = doc.get('content', doc['title'])

    collection.add(
        ids=[doc_id],
        documents=[content],
        metadatas=[{
            'source': 'elsakerhetsverket',
            'title': doc['title'],
            'url': doc['url'],
            'type': doc['type']
        }]
    )

print(f"Imported {len(data['documents'])} documents")
```

---

## ChromaDB Segfault Troubleshooting

**Problem:** ChromaDB PersistentClient segfaultar (exit code 139)

**Möjliga lösningar:**
1. Reinstallera ChromaDB: `pip install --force-reinstall chromadb`
2. Använd Docker-version av ChromaDB
3. Uppgradera/downgradera Python (testat med 3.x)
4. Kontrollera SQLite-version: `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"`
5. Kör import i separat virtualenv

---

## Dokument-exempel

### ELSÄK-FS 2022:3
```json
{
  "title": "ELSÄK-FS 2022:3",
  "url": "https://www.elsakerhetsverket.se/om-oss/lag-och-ratt/foreskrifter/elsak-fs-2022-3/...",
  "type": "föreskrift",
  "format": "html",
  "content": "Elsäkerhetsverkets föreskrifter och allmänna råd om innehavarens kontroll av starkströmsanläggningar och elektriska utrustningar..."
}
```

### Vägledning för fortlöpande kontroll
```json
{
  "title": "Vägledning för fortlöpande kontroll",
  "url": "https://www.elsakerhetsverket.se/vagledning-fortlopande-kontroll/",
  "type": "vägledning",
  "format": "html",
  "content": "Vägledning för fortlöpande kontroll enligt ELSÄK-FS 2022:3..."
}
```

---

## Nästa Steg

1. **Fixa ChromaDB segfault** (systemadmin-uppgift)
2. **Kör elsak_import_to_chromadb.py** när ChromaDB fungerar
3. **Verifiera import:** `collection.query(query_texts=["ELSÄK-FS"])`
4. **Expandera scraper** (om fler publikationer behövs):
   - `/om-oss/publikationer/`
   - `/om-oss/publikationer/print-on-demand/`

---

## Harvest Summary

| Metric | Value |
|--------|-------|
| Total Documents | 34 |
| Föreskrifter | 27 |
| Vägledningar | 7 |
| Duration | 27.5s |
| Status | ✓ JSON Ready, ✗ ChromaDB Blocked |
