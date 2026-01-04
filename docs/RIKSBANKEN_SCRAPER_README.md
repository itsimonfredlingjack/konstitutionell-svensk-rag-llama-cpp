# Riksbanken Scraper

Komplett scraping-och indexerings-workflow för Riksbankens publikationer.

## Resultat

- **Status**: OK
- **Dokument hittade**: 111
- **Dokument indexerade**: 111
- **Fel**: 0
- **Tidsstämpel**: 2025-12-07 18:39:17

## Publikationstyper som scrapats

1. **Penningpolitiska rapporter** (31 dokument)
   - Penningpolitiska rapporter (kvartalsvisa)
   - Penningpolitiska uppdateringar

2. **Publikationer** (21 dokument)
   - Diverse publikationer från Riksbanken

3. **Ekonomiska kommentarer** (34 dokument)
   - Analytiska kommentarer och fördjupningar

4. **Finansiell stabilitet** (25 dokument)
   - Finansiella stabilitetsrapporter

## ChromaDB

- **Path**: `/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data`
- **Collection**: `swedish_gov_docs`
- **Embedding model**: `KBLab/sentence-bert-swedish-cased`
- **Totalt i collection**: 305,125 dokument
- **Riksbanken-dokument**: 111

## Scripts

### Komplett workflow (rekommenderad)
```bash
python3 scrape_and_index_riksbanken.py
```

Detta script:
1. Scraper alla publikationer från riksbank.se
2. Extraherar metadata (titel, datum, typ, URL)
3. Genererar embeddings med svensk BERT-modell
4. Indexerar till ChromaDB

### Separata steg (för debugging)

**1. Endast scraping:**
```bash
python3 scrape_riksbanken_simple.py
```
Output: JSON-fil med alla publikationer

**2. Endast indexering:**
```bash
python3 index_to_chromadb.py riksbanken_scrape_YYYYMMDD_HHMMSS.json
```

**3. Verifiering:**
```bash
python3 verify_chromadb.py
```

**4. Snabb räkning (för testing):**
```bash
python3 quick_count_riksbanken.py
```

## Metadata-struktur

Varje dokument i ChromaDB har följande metadata:

```json
{
  "source": "riksbanken",
  "title": "Penningpolitisk rapport september 2025",
  "url": "https://www.riksbank.se/globalassets/...",
  "pub_type": "penningpolitisk_rapport",
  "date": "2025-09",
  "authors": "Riksbanken"
}
```

## Nästa steg

För att scrapa andra myndigheter, använd samma mönster:

1. Kopiera `scrape_and_index_riksbanken.py`
2. Uppdatera `PUBLICATION_URLS` med myndighetens sidor
3. Uppdatera `SOURCE_NAME`
4. Anpassa scraping-logiken för deras HTML-struktur
5. Kör!

## Output-filer

- `riksbanken_final_YYYYMMDD_HHMMSS.json` - Slutligt resultat
- `riksbanken_scrape_YYYYMMDD_HHMMSS.json` - Endast scraping-resultat (från simple-versionen)

## Prestanda

- **Scraping**: ~10 sekunder
- **Indexering**: ~1 minut (för 111 dokument)
- **Total tid**: ~1.5 minuter

## Begränsningar

- PDF-text extraheras INTE (för snabbare körning)
- Endast metadata och URL indexeras
- För full-text PDF-extraktion, använd `scrape_riksbanken.py` (långsammare)

## Dependencies

```bash
pip install beautifulsoup4 lxml chromadb sentence-transformers requests
```
