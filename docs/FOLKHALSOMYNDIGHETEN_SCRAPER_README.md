# Folkhälsomyndigheten Scraper

Komplett scraper för Folkhälsomyndighetens publikationer till ChromaDB.

## Översikt

**Status:** ✅ KLAR - 977 publikationer indexerade
**Threshold:** 100 dokument (MET)
**ChromaDB docs:** 1000+ dokument från Folkhälsomyndigheten

## Användning

```bash
cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
source venv/bin/activate
python3 scrape_folkhalsomyndigheten_v2.py
```

## Vad scrapar scriptet?

- **Källa:** folkhalsomyndigheten.se/publikationer-och-material/publikationer/
- **Metod:** Paginerad sökning (60 sidor, parameter `pn`)
- **Innehåll:** Rapporter, statistik, rekommendationer, kunskapsstöd

### Fokusområden

- ANDTS (alkohol, droger, doping, tobak, spel)
- Smittskydd och vaccinationer
- COVID-19 dokument
- Mental hälsa och suicidprevention
- Levnadsvanor och livsmiljö
- Skolbarns hälsa
- Antibiotikaresistens (Swedres)
- HALT (vårdrelaterade infektioner)

## Tekniska detaljer

### ChromaDB Integration

```python
# Collection
collection_name = "swedish_gov_docs"
chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

# Embedding
model = "all-MiniLM-L6-v2"  # 384 dimensions
```

### Metadata Structure

Varje dokument lagras med:

```json
{
  "source": "folkhalsomyndigheten",
  "title": "Publikationens titel",
  "url": "https://www.folkhalsomyndigheten.se/...",
  "pub_type": "publikation",
  "date": "YYYY-MM-DD or 'Unknown'",
  "authors": "Folkhälsomyndigheten"
}
```

### Rate Limiting

- 2 sekunder delay mellan sidförfrågningar
- Exponential backoff vid HTTP-fel
- Max 3 retry-försök per sida

## Utdata

### JSON-rapport

```
folkhalsomyndigheten_final_YYYYMMDD_HHMMSS.json
```

Innehåller:
- Antal dokument hittade
- Antal dokument indexerade
- Status (OK/FLAGGAD)
- Eventuella fel
- Timestamp

### Log-fil

```
folkhalsomyndigheten_v2_paginated.log
```

Detaljerad scraping-logg.

## Kända begränsningar

1. **PDF-extraktion:** Endast PDF-länkar sparas, inte full-text innehåll
2. **Duplicerade länkar:** Vissa sidor innehåller samma publikation flera gånger
3. **Pagination:** Siten rapporterar 1257 publikationer, scriptet hämtade 977 unika

## Förbättringsmöjligheter

- [ ] Full-text PDF extraction (PyPDF2 implementerad men avstängd för hastighet)
- [ ] Kategorisering baserad på ämnesområden
- [ ] Författarextraktion där tillämpligt
- [ ] Scraping av borttagna publikationer (separat arkiv)

## Verifiering

Kolla antal dokument i ChromaDB:

```python
import chromadb

client = chromadb.PersistentClient(path='chromadb_data')
coll = client.get_collection('swedish_gov_docs')

results = coll.get(where={'source': 'folkhalsomyndigheten'}, limit=1000)
print(f"Antal dokument: {len(results['ids'])}")
```

## Exempel: Semantic Search

```python
import chromadb
from sentence_transformers import SentenceTransformer

client = chromadb.PersistentClient(path='chromadb_data')
coll = client.get_collection('swedish_gov_docs')
model = SentenceTransformer('all-MiniLM-L6-v2')

# Sök efter COVID-19 relaterade dokument
query = "COVID-19 vaccination rekommendationer"
query_embedding = model.encode(query).tolist()

results = coll.query(
    query_embeddings=[query_embedding],
    where={'source': 'folkhalsomyndigheten'},
    n_results=5
)

for i, (title, url) in enumerate(zip(
    [m['title'] for m in results['metadatas'][0]],
    [m['url'] for m in results['metadatas'][0]]
)):
    print(f"{i+1}. {title}")
    print(f"   {url}\n")
```

## Maintenance

### Uppdatera data

Kör scriptet igen för att hämta nya publikationer:

```bash
python3 scrape_folkhalsomyndigheten_v2.py
```

Duplicerade dokument skippas automatiskt baserat på URL-hash.

### Rensa gamla data

```python
import chromadb

client = chromadb.PersistentClient(path='chromadb_data')
coll = client.get_collection('swedish_gov_docs')

# Ta bort alla Folkhälsomyndigheten-dokument
results = coll.get(where={'source': 'folkhalsomyndigheten'})
if results['ids']:
    coll.delete(ids=results['ids'])
```

## Licens & Källa

Data från Folkhälsomyndigheten är offentlig svensk myndighetsdata.

**Källa:** https://www.folkhalsomyndigheten.se
**Scraper:** Simon's Constitutional AI Project
**Datum:** 2025-12-07
