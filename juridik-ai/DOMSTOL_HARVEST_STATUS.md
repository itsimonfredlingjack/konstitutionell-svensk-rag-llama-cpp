# Domstolsverket Harvest Status

## CURRENT STATUS: BLOCKED - REQUIRES MANUAL API MAPPING

### Problem

Domstol.se använder en **JavaScript Single Page Application (SPA)** för sin nya söktjänst "Sök rättspraxis" (lanserad mars 2025). Detta betyder att:

1. HTML-innehåll laddas dynamiskt via JavaScript
2. Standard HTTP requests får endast en minimal HTML-skal (586 bytes)
3. Faktiska data hämtas via interna API-anrop som körs i webbläsaren

### Attempted Solutions

#### 1. Direct API Inspection
- **Försök:** WebFetch på `rattspraxis.etjanst.domstol.se`
- **Resultat:** Minimal HTML, inget data-innehåll
- **Slutsats:** SPA, kräver JavaScript execution

#### 2. Open Data Portal
- **Försök:** Dataportal.se dataset 601_3755 "Rättspraxis från Sveriges Domstolar"
- **Resultat:** Även dataportalen är ett SPA
- **Slutsats:** Ingen direkt JSON/API-access

#### 3. Legacy Pages (före mars 2025)
- **Försök:** `domstol.se/hogsta-domstolen/avgoranden2/`
- **Resultat:** 65KB HTML men ingen PDF-länkar eller måln ummer
- **Slutsats:** Också JavaScript-drivet

#### 4. RSS Feeds
- **Försök:** Söka efter RSS-feeds
- **Resultat:** Inga `<link type="application/rss+xml">` hittades
- **Slutsats:** RSS kanske finns men kräver manual sökning

### Required Next Steps

För att implementera Domstolsverket-scraping behövs **EN** av följande lösningar:

#### OPTION A: Browser Automation (RECOMMENDED)
```bash
pip install selenium playwright
playwright install chromium
```

**Implementation:**
- Använd Playwright/Selenium för att ladda sidan
- Vänta på att JavaScript renderar innehållet
- Extrahera data från DOM
- Implementera samma GDPR-checks som redan finns

**Pros:**
- ✓ Fungerar med alla JavaScript-sidor
- ✓ Kan navigera, klicka, fylla formulär

**Cons:**
- ✗ Långsammare (måste vänta på JavaScript)
- ✗ Kräver headless browser

#### OPTION B: Manual API Reverse Engineering
1. Öppna https://rattspraxis.etjanst.domstol.se/ i Chrome
2. Öppna DevTools (F12) → Network tab
3. Gör en sökning
4. Identifiera XHR/Fetch requests till API
5. Dokumentera endpoints, parametrar, headers
6. Implementera direkt API-calls i Python

**Pros:**
- ✓ Mycket snabbare än browser automation
- ✓ Lättare att rate-limit:a

**Cons:**
- ✗ Kräver manuell inspektion
- ✗ API kan ändras utan varning

#### OPTION C: Contact Domstolsverket
- Be om officiell API-dokumentation
- Fråga om bulk-export av domar
- Referera till Open Data-portalen

**Pros:**
- ✓ Officiellt stöd
- ✓ Mer hållbart långsiktigt

**Cons:**
- ✗ Kan ta veckor/månader
- ✗ Kanske inte finns

### Current Implementation

Scripten som skapats:

1. **`pipelines/domstol_scraper.py`**
   - TEMPLATE implementation
   - GDPR anonymization checks ✓
   - Rate limiting (15s) ✓
   - Session management ✓
   - **SAKNAS:** Faktisk API-integration

2. **`domstol_harvest.py`**
   - ChromaDB integration ✓
   - Statistics tracking ✓
   - Multi-court support ✓
   - **SAKNAS:** Funktionell scraper

### Test Plan (When Unblocked)

```bash
# 1. Test GDPR checks
python3 -c "
from pipelines.domstol_scraper import DomstolScraper
scraper = DomstolScraper()

# Test anonymization check
text_with_pii = 'John Doe, 850415-1234, john@example.com'
is_safe, warnings = scraper._check_gdpr_compliance(text_with_pii)
print(f'GDPR Safe: {is_safe}, Warnings: {warnings}')
"

# 2. Test ChromaDB connection
python3 -c "
from cli.brain import get_brain
brain = get_brain()
print(f'ChromaDB collection: {brain.collection.name}')
print(f'Current count: {brain.collection.count()}')
"

# 3. Run harvest (once API is mapped)
python3 domstol_harvest.py
```

### SIMON: Rekommendation

**PRIORITET:** Implementera OPTION B (Manual API Reverse Engineering)

**STEG:**
1. Öppna https://rattspraxis.etjanst.domstol.se/ i browser
2. DevTools → Network → XHR
3. Sök efter "miljö" (random legal term)
4. Hitta API request (troligen till `/api/search` eller liknande)
5. Dokumentera:
   - Endpoint URL
   - HTTP method (GET/POST)
   - Request parameters
   - Response format (JSON structure)
   - Pagination mechanism
6. Uppdatera `domstol_scraper.py` med faktiska API-calls

**ESTIMAT:** 30-60 minuter manuellt arbete

**ALTERNATIV:** Om du har tillgång till en webbläsare med DevTools, kan du göra detta själv och ge mig API-specifikationen.

---

## Data Sources (for reference)

- [Sök rättspraxis](https://rattspraxis.etjanst.domstol.se/sok/sokning)
- [Högsta domstolen avgöranden](https://www.domstol.se/hogsta-domstolen/avgoranden/)
- [Högsta förvaltningsdomstolen avgöranden](https://www.domstol.se/hogsta-forvaltningsdomstolen/avgoranden/)
- [Dataportal.se: Rättspraxis från Sveriges Domstolar](https://www.dataportal.se/datasets/601_3755)
- [Avgöranden före mars 2025 (HD)](https://www.domstol.se/hogsta-domstolen/avgoranden2/)
- [Avgöranden före mars 2025 (HFD)](https://www.domstol.se/hogsta-forvaltningsdomstolen/avgoranden2/)

---

**Status:** FLAGGAD - Kräver manuell API-mapping eller browser automation
**Docs Found:** 0
**Docs Indexed:** 0
**Next Action:** Manual API reverse engineering ELLER Playwright implementation
