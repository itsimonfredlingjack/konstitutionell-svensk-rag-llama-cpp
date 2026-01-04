# Agent-orkestrering för insamling av svensk myndighetsinformation

AI-agenter kan effektivt samla och strukturera svenska offentliga handlingar genom en hierarkisk orkestreringsmodell kombinerat med MCP-servrar, där **Riksdagens öppna REST-API** utgör den mest tillgängliga datakällan med över 500 000 dokument. Denna rapport definierar en komplett metodik för att bygga ett robust, lagligt och etiskt system för automatiserad insamling av myndighetsmaterial i Sverige.

Den svenska offentlighetsprincipen från 1766 ger världens äldsta rätt till insyn i offentliga handlingar, men digital leverans är inte garanterad – myndigheter kan uppfylla begäran genom papperskopior. **GDPR och OSL 21:7** kan begränsa storskalig automatiserad insamling av personuppgifter, även från offentliga källor. Systemet måste därför balansera teknisk effektivitet med juridisk hänsyn och respekt för serverresurser.

## Orkestreringsmönster för multi-agent research

Den optimala arkitekturen för svensk myndighetsinsamling bygger på **hierarkisk orkestrering** med en lead orchestrator som koordinerar specialiserade worker-agenter. Denna modell ger transparent reasoning, kvalitetskontroll och möjlighet till human-in-the-loop vid känsliga beslut.

Model Context Protocol (MCP) fungerar som kommunikationsstandard mellan agenter och externa verktyg, där JSON-RPC 2.0-meddelanden transporterar verktygsanrop, resurser och prompts. MCP reducerar integrationskomplexiteten från N×M till N+M genom standardiserade primitiver. Flera ramverk stödjer MCP-baserad multi-agent-koordinering: **mcp-agent** från lastmile-ai implementerar alla Anthropics agentmönster med Temporal-baserad durability, medan **claude-flow** erbjuder 64 specialiserade agenter med swarm-orkestrering i mesh- eller hierarkisk topologi.

En effektiv rollfördelning för svensk myndighetsinsamling struktureras enligt följande modell:

| Agentroll | Modellnivå | Ansvar |
|-----------|-----------|--------|
| Orchestrator | Opus 4.5 | Uppgiftsdekomponering, koordinering, slutsyntes |
| Crawler-agent | Haiku/Lokal | URL-insamling, rådata-hämtning från myndigheter |
| Metadata-agent | Haiku/Lokal | Extraktion av diarienummer, SFS-nummer, datum |
| Dokumentanalys-agent | Sonnet/Lokal | Textutvinning, sammanfattning, klassificering |
| Verifierings-agent | Sonnet | Kvalitetskontroll, faktakontroll, dubblettdetektering |

Pipeline-orkestrering passar dokumentprocessing där varje steg bygger på föregående: *crawler → parser → analyzer → validator → reporter*. Fan-out/fan-in lämpar sig för parallell analys av samma dokument från flera perspektiv. Handoff-mönstret aktiveras när en agent upptäcker att uppgiften kräver specialist­kompetens den saknar.

### MCP-konfiguration för Claude Code

Grundkonfigurationen för ett myndighetsinsamlingssystem kräver tre MCP-servrar:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/documents/myndigheter"]
    },
    "fetch": {
      "command": "npx", 
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

Memory-servern möjliggör delat minne mellan agenter för att undvika redundant arbete, medan filesystem-servern hanterar lokalt dokumentlager. För avancerad webbskrapning med JavaScript-rendering rekommenderas Firecrawl MCP-servern.

### Modellrouting för kostnadseffektivitet

RouteLLM-ramverket från LMSYS demonstrerar att **upp till 85% kostnadsreduktion** är möjlig med bibehållen kvalitet genom intelligent routing. Implementera en komplexitetsklassificerare som dirigerar enkla uppgifter till Haiku eller lokala modeller (Qwen 3 14B, Devstral 24B) medan komplexa resonemang går till Opus:

```python
def route_to_model(task_complexity: str, task_type: str):
    if task_type == "bulk_crawling":
        return "local/qwen-3-14b"  # Volymeffektivitet
    elif task_complexity == "high" or task_type in ["qa", "synthesis"]:
        return "claude-opus"  # Komplex reasoning
    elif task_type == "code_generation":
        return "claude-sonnet"  # Balans kapabilitet/kostnad
    else:
        return "claude-haiku"  # Snabb, kostnadseffektiv
```

## Svenska myndigheters webbstrukturer och datamönster

Riksdagens öppna data utgör den mest strukturerade källan för svensk myndighetsinformation. REST-API:et på `http://data.riksdagen.se/` erbjuder direkt åtkomst till propositioner, motioner, kammarprotokoll, utskottsbetänkanden och voteringar i XML, JSON och CSV-format. Täckningen sträcker sig tillbaka till **1867**, med diarium från september 2017.

Grundläggande API-anrop till Riksdagen konstrueras med URL-parametrar:

```python
import httpx

async def fetch_riksdag_documents(doc_type: str, year: str, limit: int = 100):
    """Hämta dokument från Riksdagens API"""
    base_url = "http://data.riksdagen.se/dokumentlista/"
    params = {
        "rm": year,           # Riksmöte, t.ex. "2024/25"
        "typ": doc_type,      # "mot" (motion), "prop" (proposition), etc.
        "sz": limit,
        "sort": "datum",
        "utformat": "json"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(base_url, params=params)
        return response.json()

# Dokumenttyper: mot, prop, bet, rskr, sou, ds, skr, dir
```

Regeringskansliets rättsdatabaser tillhandahåller lagar med ändringsmarkeringar. SFS-dokument publiceras elektroniskt sedan april 2018 på svenskforfattningssamling.se, medan äldre versioner (1998-2018) finns på `rkrattsdb.gov.se/sfspdf/`. Lagrummet.se aggregerar lagstiftning, förarbeten och rättspraxis från Domstolsverket.

### Dokumentidentifieringssystem

| System | Format | Exempel |
|--------|--------|---------|
| SFS (lag/förordning) | [År]:[Löpnummer] | 1994:200 |
| Proposition | Prop. [Riksmöte]:[Nr] | Prop. 2024/25:87 |
| SOU (utredning) | SOU [År]:[Nr] | SOU 2021:58 |
| Ds (departement) | Ds [År]:[Nr] | Ds 2022:25 |
| Diarienummer | [Dep][År]/[Nr] | Ju2020/04654 |

Diarienummer är nyckeln för att begära specifika handlingar. Formatet varierar mellan myndigheter men följer generellt mönstret *departementskod + år + löpnummer*.

### Dataportalen och öppna data

Sveriges dataportal (dataportal.se) samlar **7 700+ datasets** från offentlig sektor, hanterat av DIGG. Licensen är vanligtvis CC0, vilket tillåter fri användning utan attributionskrav. SCB:s API har specifik rate limiting på **max 10 requests per 10 sekunder per IP**.

## Rättslig ram för automatiserad insamling

Offentlighetsprincipen i Tryckfrihetsförordningen 2 kap garanterar rätten att ta del av allmänna handlingar. En handling är allmän om den uppfyller tre kriterier: den utgör en *handling* (skrift, bild eller teknisk upptagning), *förvaras hos myndighet*, och är *inkommen till eller upprättad* vid myndigheten. Digitala dokument i databaser omfattas när de kan göras tillgängliga med befintliga tekniska hjälpmedel.

**Utskriftsundantaget** i TF 2:16 är kritiskt för automatiserad insamling: myndigheter är *inte skyldiga* att lämna ut digitala dokument i elektronisk form utan kan uppfylla begäran genom papperskopior. Syftet är att förhindra storskalig datainsamling som kan kränka personlig integritet. Dock finns inget *förbud* mot digital leverans – många myndigheter, särskilt domstolar, mejlar rutinmässigt dokument när integritets­hänsyn saknas.

Offentlighets- och sekretesslagen (OSL) begränsar tillgången till vissa handlingar. **OSL 21:7** är särskilt relevant för AI-system: sekretess gäller för personuppgifter om det kan antas att mottagaren kommer behandla dem i strid med GDPR. Myndigheten får fråga om ändamålet vid sekretessprövning. Praktiska implikationer för automatiserade system:

- Anta icke-sekretess för publicerade lagar, domar och protokoll
- Var försiktig med namngivna individer, hälso-/socialdata, affärshemligheter
- Undvik systematisk insamling av personuppgifter utan explicit rättslig grund

GDPR artikel 86 tillåter utlämnande av personuppgifter i offentliga handlingar enligt nationell lag, men *efterföljande behandling* kräver separat rättslig grund – typiskt berättigat intresse (art. 6.1.f) för privata aktörer, med krav på intresseavvägning.

### Upphovsrätt och myndighetsdata

Upphovsrättslagen 9 § undantar författningar, myndighetsbeslut och yttranden från upphovsrätt. Lagar, förordningar och domslut är fritt användbara. **Undantag:** kartor, bildkonst, musikverk, dikter och datorprogram behåller skydd även när de ingår i offentliga handlingar.

Robots.txt är **inte juridiskt bindande** i svensk rätt utan en samarbetsbaserad konvention. Att ignorera den kan dock indikera ond tro och vara relevant i civilrättsliga tvister. Bästa praxis är att respektera direktivet som etisk standard och dokumentera eventuella avvikelser.

## Teknisk implementation

### HTTP-klient med retry och rate limiting

```python
import httpx
import asyncio
from tenacity import retry, stop_after_attempt, wait_random_exponential
from ratelimit import limits, sleep_and_retry

class SwedishGovScraper:
    def __init__(self, requests_per_minute: int = 6):
        self.client = httpx.AsyncClient(
            headers={
                'User-Agent': 'ConstitutionalNerdyAI/1.0 (research@example.com)',
                'Accept-Language': 'sv-SE,sv;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xml,application/json'
            },
            timeout=60,
            follow_redirects=True,
            http2=True
        )
        self._delay = 60 / requests_per_minute
    
    @retry(
        wait=wait_random_exponential(min=2, max=60),
        stop=stop_after_attempt(5)
    )
    async def fetch(self, url: str) -> httpx.Response:
        response = await self.client.get(url)
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            await asyncio.sleep(retry_after)
            raise httpx.HTTPStatusError("Rate limited", request=response.request, response=response)
        response.raise_for_status()
        await asyncio.sleep(self._delay)  # Respektera rate limit
        return response
    
    async def close(self):
        await self.client.aclose()
```

### PDF-processering med svensk teckenstöd

PyMuPDF (fitz) ger **5-10x snabbare** textextraktion än alternativ med fullständigt UTF-8-stöd för svenska tecken. För OCR av scannade dokument krävs Tesseracts svenska språkpaket:

```python
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

def extract_swedish_pdf(pdf_path: str, use_ocr: bool = False) -> str:
    doc = fitz.open(pdf_path)
    full_text = []
    
    for page in doc:
        text = page.get_text("text")
        
        # Om sidan saknar text, försök OCR
        if not text.strip() and use_ocr:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes()))
            text = pytesseract.image_to_string(img, lang='swe', config='--psm 1')
        
        full_text.append(text)
    
    doc.close()
    return "\n".join(full_text)

def extract_tables_from_pdf(pdf_path: str) -> list:
    """Extrahera tabeller med pdfplumber"""
    import pdfplumber
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            tables.extend(page_tables)
    return tables
```

### Anpassad MCP-server för dokumentinsamling

```python
from mcp.server.fastmcp import FastMCP
import httpx
import fitz
from dataclasses import dataclass
from datetime import datetime

mcp = FastMCP(name="SwedishGovDocCollector")

@dataclass
class DocumentMetadata:
    doc_id: str
    source: str
    title: str
    doc_type: str
    date: datetime
    sfs_number: str = None
    diarienummer: str = None

@mcp.tool
async def fetch_riksdag_proposition(prop_number: str) -> dict:
    """Hämta en proposition från Riksdagen, t.ex. '2024/25:87'"""
    url = f"http://data.riksdagen.se/dokument/{prop_number.replace('/', '')}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params={"utformat": "json"})
        return response.json()

@mcp.tool
def parse_sfs_document(pdf_path: str) -> dict:
    """Extrahera text och metadata från SFS-dokument"""
    text = extract_swedish_pdf(pdf_path)
    # Extrahera SFS-nummer från första raden
    import re
    sfs_match = re.search(r'SFS\s*(\d{4}:\d+)', text)
    return {
        "sfs_number": sfs_match.group(1) if sfs_match else None,
        "content": text,
        "pages": fitz.open(pdf_path).page_count
    }

@mcp.tool
async def search_dataportal(query: str, limit: int = 10) -> list:
    """Sök i Sveriges dataportal"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.dataportal.se/api/search",
            params={"q": query, "limit": limit}
        )
        return response.json()

if __name__ == "__main__":
    mcp.run()
```

### Vektordatabas för dokumentsökning

ChromaDB med svenska sentence embeddings möjliggör semantisk sökning i insamlade dokument:

```python
import chromadb
from sentence_transformers import SentenceTransformer

# KBLab's svenska BERT-modell
model = SentenceTransformer('KBLab/sentence-bert-swedish-cased')
client = chromadb.PersistentClient(path="./swedish_docs_db")
collection = client.get_or_create_collection(
    name="myndighetshandlingar",
    metadata={"hnsw:space": "cosine"}
)

def index_document(doc_id: str, text: str, metadata: dict):
    embedding = model.encode(text).tolist()
    collection.add(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )

def semantic_search(query: str, n_results: int = 10) -> list:
    query_embedding = model.encode(query).tolist()
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
```

## Ansvarsfull datainsamling

Respektera myndigheternas serverresurser med konservativ rate limiting. För svenska myndighetssidor rekommenderas **5-10 sekunders fördröjning** mellan requests och max en samtidig anslutning. Adaptiv rate limiting justerar fördröjningen baserat på serverrespons:

```python
class AdaptiveRateLimiter:
    def __init__(self, base_delay: float = 10.0, max_delay: float = 120.0):
        self.current_delay = base_delay
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    async def adapt(self, response: httpx.Response, response_time: float):
        if response.status_code == 429:
            self.current_delay = min(self.current_delay * 2, self.max_delay)
        elif response_time > 10:  # Långsam respons = serverbelastning
            self.current_delay = min(self.current_delay * 1.5, self.max_delay)
        elif response.status_code == 200 and response_time < 2:
            self.current_delay = max(self.current_delay * 0.9, self.base_delay)
        
        await asyncio.sleep(self.current_delay)
```

Circuit breaker-mönstret förhindrar fortsatta anrop när upprepade fel indikerar problem. Efter fem misslyckanden öppnas brytaren och avvisar requests under en återhämtningsperiod. Exponentiell backoff med jitter undviker thundering herd-effekter när fel uppstår.

Caching minimerar redundanta requests. Riksdagens dokument ändras sällan efter publicering – cache-TTL på 24-48 timmar är rimligt för befintliga handlingar. Inkrementell crawling spårar redan hämtade URL:er och processar endast nytt innehåll.

## Referensarkitektur

```
constitutional-nerdy-ai/
├── orchestrator/
│   ├── coordinator.py       # Hierarkisk orchestrator (Opus)
│   ├── router.py            # Modellrouting-logik
│   └── task_queue.py        # Uppgiftshantering
├── agents/
│   ├── crawler/             # Haiku/lokal – URL-insamling
│   ├── metadata/            # Haiku/lokal – Metadataextraktion
│   ├── analyzer/            # Sonnet – Dokumentanalys
│   └── validator/           # Sonnet – Kvalitetskontroll
├── scrapers/
│   ├── riksdag.py           # Riksdagens API-integration
│   ├── regeringen.py        # Regeringskansliets sidor
│   ├── domstol.py           # Domstolsverkets rättsinformation
│   └── kommun.py            # Kommunwebbplatser
├── parsers/
│   ├── pdf_parser.py        # PyMuPDF + OCR
│   ├── html_parser.py       # BeautifulSoup/lxml
│   └── metadata_extractor.py
├── storage/
│   ├── vector_store.py      # ChromaDB-integration
│   ├── document_store.py    # Fillagring + metadata
│   └── deduplication.py     # SHA-256 hash-baserad
├── mcp/
│   ├── server.py            # Anpassad MCP-server
│   └── tools.py             # Verktygsimplementationer
└── config/
    ├── rate_limits.yaml     # Per-myndighet rate limits
    └── robots_cache/        # Cachade robots.txt
```

Systemet integreras med befintlig n8n-infrastruktur genom HTTP-trigger-noder som anropar MCP-servern eller direkta Python-funktioner. N8n hanterar schemaläggning och övervakning medan AI-agenterna utför den faktiska insamlingen och analysen.

## Risker och mitigering

Tre huvudrisker kräver aktiv hantering:

1. **Sekretessöverträdelse** – Automatiska system kan oavsiktligt samla sekretesskyddade uppgifter. Mitigering: Implementera filtrering för personnummer, hälsodata och affärshemligheter; begränsa insamling till publicerat material på öppna webbsidor.

2. **Serverbelastning** – Aggressiv crawling kan störa myndigheters tjänster. Mitigering: Konservativ rate limiting (5-10s delay), off-peak schemaläggning (03:00), circuit breakers vid upprepade fel.

3. **GDPR-överträdelse** – Storskalig behandling av personuppgifter från offentliga källor kräver rättslig grund. Mitigering: Dokumentera berättigat intresse-bedömning, anonymisera där möjligt, implementera retention limits.

## Nästa steg för implementation

Börja med Riksdagens API som primär datakälla – det är väldokumenterat, öppet och kräver ingen autentisering. Bygg först en minimal crawler-agent med rate limiting och retry-logik, sedan expandera till metadata-extraktion och dokumentanalys. Implementera MCP-servern för att möjliggöra integration med Claude Code. Etablera vektordatabasen med KBLabs svenska embeddings för att aktivera semantisk sökning i det insamlade materialet. Övervaka systemets beteende kontinuerligt och justera rate limits baserat på faktisk serverrespons från varje myndighet.
