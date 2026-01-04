# Swedish Government Document Scrapers

Mega-scraping operation för svenska myndighetsdokument till ChromaDB.

## SCB (Statistiska Centralbyrån)

### Quick Start

```bash
# Quick test (1200 tabeller, ~20-30 minuter)
python3 scb_quick_test.py

# Komplett scraping (5200+ tabeller, ~2 timmar)
python3 scb_scraper.py
```

### API Information

- **Endpoint**: `https://statistikdatabasen.scb.se/api/v2`
- **Dokumentation**: [SCB PxWebApi 2.0](https://www.scb.se/en/services/open-data-api/pxwebapi/pxapi-2.0)
- **Rate Limit**: 10 requests per 10 seconds
- **Totalt antal tabeller**: ~5204 (December 2025)

### Implementation Details

**Features:**
- PxWebApi 2.0 integration
- Metadata extraction för varje tabell
- Svenska embeddings via `KBLab/sentence-bert-swedish-cased`
- ChromaDB indexing för semantisk sökning
- Rate limiting (1s delay)
- Retry logic med exponentiell backoff
- GPU-accelererad embedding generation

**Output:**
- ChromaDB collection: `swedish_gov_docs`
- Metadata: source="scb", table_id, updated, category
- Report: JSON med status, antal dokument, fel

### Configuration

I `scb_scraper.py`:

```python
RATE_LIMIT_DELAY = 1.0  # Sekunder mellan requests
MIN_EXPECTED_DOCS = 1000  # Flagga om färre
MAX_TABLES_LIMIT = None  # Begränsa antal (None = alla)
```

### Example Output

```json
{
  "myndighet": "SCB",
  "status": "OK",
  "docs_found": 5204,
  "docs_indexed": 5204,
  "errors": []
}
```

### Troubleshooting

**ChromaDB readonly error:**
```bash
chmod 664 chromadb_data/chroma.sqlite3
```

**Rate limiting:**
API:et tillåter max 10 requests/10s. Scriptet använder 1s delay för säkerhetsmarginal.

**Memory:**
Embedding model tar ~2GB VRAM. Kör på GPU för bästa prestanda.

## ChromaDB Setup

```bash
# ChromaDB path
/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data

# Collection
swedish_gov_docs

# Embedding model
KBLab/sentence-bert-swedish-cased (svensk BERT)
```

## Future Scrapers

- Riksdagen API
- Regeringskansliet
- Domstolsverket
- Sveriges Dataportal

## Architecture

```
scrapers/
├── scb_scraper.py          # Huvudscript för SCB
├── scb_quick_test.py       # Quick test (1200 tabeller)
├── README.md               # Denna fil
└── [future]_scraper.py     # Andra myndigheter
```
