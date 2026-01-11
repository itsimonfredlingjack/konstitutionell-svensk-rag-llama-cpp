#!/usr/bin/env python3
"""
SCB (Statistiska Centralbyrån) API Scraper
Hämtar publikationer och statistiska rapporter via PxWebApi 2.0
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import chromadb
import httpx
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential

# Konfiguration
SCB_API_BASE = "https://statistikdatabasen.scb.se/api/v2"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"
RATE_LIMIT_DELAY = 1.0  # SCB: max 10 requests per 10 seconds, vi kör 1s för att vara inom gränsen
MIN_EXPECTED_DOCS = 1000  # Flagga om färre än detta
MAX_TABLES_LIMIT = None  # Sätt till ett tal för att begränsa (None = alla)

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("SCB_Scraper")


class SCBScraper:
    """Scraper för SCB PxWebApi 2.0"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "ConstitutionalNerdyAI/1.0 SCB-Scraper (research purposes)",
                "Accept": "application/json",
                "Accept-Language": "sv-SE,sv;q=0.9",
            },
            timeout=60.0,
            follow_redirects=True,
        )
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.stats = {"tables_found": 0, "tables_processed": 0, "docs_indexed": 0, "errors": []}

    async def initialize(self):
        """Initialisera embedding model och ChromaDB"""
        logger.info("Laddar embedding model: %s", EMBEDDING_MODEL)
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)

        logger.info("Ansluter till ChromaDB: %s", CHROMADB_PATH)
        self.chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
        )
        logger.info("ChromaDB collection: %s", COLLECTION_NAME)

    @retry(wait=wait_exponential(min=2, max=120), stop=stop_after_attempt(5), reraise=True)
    async def _fetch_json(self, url: str, params: dict | None = None) -> dict:
        """Hämta JSON från API med retry och rate limiting"""
        try:
            response = await self.client.get(url, params=params)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning("Rate limited, väntar %s sekunder", retry_after)
                await asyncio.sleep(retry_after)
                raise httpx.HTTPStatusError(
                    "Rate limited", request=response.request, response=response
                )

            response.raise_for_status()
            await asyncio.sleep(RATE_LIMIT_DELAY)
            return response.json()

        except httpx.HTTPError as e:
            logger.error("HTTP error för %s: %s", url, e)
            self.stats["errors"].append(f"HTTP error: {url} - {e!s}")
            raise

    async def fetch_all_tables(self) -> list[dict]:
        """Hämta alla tillgängliga tabeller från SCB"""
        logger.info("Hämtar tabellista från SCB API...")
        all_tables = []
        page = 0
        page_size = 100

        while True:
            url = f"{SCB_API_BASE}/tables"
            params = {"pageNumber": page, "pageSize": page_size}

            try:
                data = await self._fetch_json(url, params)

                # SCB returnerar data i olika format beroende på version
                # Försök extrahera tabeller från vanliga strukturer
                tables = []
                if isinstance(data, dict):
                    if "tables" in data:
                        tables = data["tables"]
                    elif "data" in data:
                        tables = data["data"]
                    elif "items" in data:
                        tables = data["items"]
                elif isinstance(data, list):
                    tables = data

                if not tables:
                    logger.info("Inga fler tabeller på sida %d", page)
                    break

                all_tables.extend(tables)
                logger.info(
                    "Hämtade %d tabeller från sida %d (totalt: %d)",
                    len(tables),
                    page,
                    len(all_tables),
                )

                # Om färre än page_size returnerades, vi är klara
                if len(tables) < page_size:
                    break

                page += 1

            except Exception as e:
                logger.error("Fel vid hämtning av tabeller sida %d: %s", page, e)
                self.stats["errors"].append(f"Table fetch page {page}: {e!s}")
                break

        self.stats["tables_found"] = len(all_tables)
        logger.info("Totalt antal tabeller funna: %d", len(all_tables))
        return all_tables

    async def fetch_table_metadata(self, table_id: str) -> dict | None:
        """Hämta detaljerad metadata för en tabell"""
        url = f"{SCB_API_BASE}/tables/{table_id}/metadata"

        try:
            metadata = await self._fetch_json(url)
            return metadata
        except Exception as e:
            logger.error("Kunde inte hämta metadata för tabell %s: %s", table_id, e)
            self.stats["errors"].append(f"Metadata fetch {table_id}: {e!s}")
            return None

    def extract_text_content(self, table: dict, metadata: dict | None) -> str:
        """Extrahera textinnehåll från tabell och metadata för indexering"""
        parts = []

        # Tabell-information
        if "id" in table:
            parts.append(f"Tabell-ID: {table['id']}")
        if "label" in table:
            parts.append(f"Rubrik: {table['label']}")
        if "text" in table:
            parts.append(f"Text: {table['text']}")
        if "description" in table:
            parts.append(f"Beskrivning: {table['description']}")
        if "updated" in table:
            parts.append(f"Uppdaterad: {table['updated']}")
        if "category" in table:
            parts.append(f"Kategori: {table['category']}")

        # Metadata om tillgänglig
        if metadata:
            if "title" in metadata:
                parts.append(f"Titel: {metadata['title']}")
            if "description" in metadata:
                parts.append(f"Metadata-beskrivning: {metadata['description']}")
            if "source" in metadata:
                parts.append(f"Källa: {metadata['source']}")
            if "variables" in metadata:
                var_names = [v.get("code", v.get("text", "")) for v in metadata["variables"]]
                parts.append(f"Variabler: {', '.join(var_names)}")

        return "\n".join(parts)

    def generate_doc_id(self, table_id: str) -> str:
        """Generera unikt dokument-ID"""
        return f"scb_{table_id}_{hashlib.sha256(table_id.encode()).hexdigest()[:8]}"

    async def index_table(self, table: dict, metadata: dict | None):
        """Indexera en tabell till ChromaDB"""
        try:
            table_id = table.get("id", str(hash(str(table))))
            doc_id = self.generate_doc_id(table_id)

            # Extrahera text
            text_content = self.extract_text_content(table, metadata)

            if not text_content.strip():
                logger.warning("Tom textinnehåll för tabell %s, hoppar över", table_id)
                return

            # Generera embedding
            embedding = self.embedding_model.encode(text_content).tolist()

            # Metadata för ChromaDB
            chroma_metadata = {
                "source": "scb",
                "table_id": table_id,
                "updated": table.get("updated", ""),
                "category": table.get("category", ""),
                "indexed_at": datetime.now().isoformat(),
            }

            # Lägg till i ChromaDB
            self.collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text_content],
                metadatas=[chroma_metadata],
            )

            self.stats["docs_indexed"] += 1

            if self.stats["docs_indexed"] % 50 == 0:
                logger.info("Indexerat %d dokument...", self.stats["docs_indexed"])

        except Exception as e:
            logger.error("Fel vid indexering av tabell %s: %s", table.get("id", "?"), e)
            self.stats["errors"].append(f"Indexing error {table.get('id', '?')}: {e!s}")

    async def process_table(self, table: dict):
        """Processera en enskild tabell"""
        table_id = table.get("id", "")

        try:
            # Hämta metadata
            metadata = await self.fetch_table_metadata(table_id)

            # Indexera
            await self.index_table(table, metadata)

            self.stats["tables_processed"] += 1

        except Exception as e:
            logger.error("Fel vid processering av tabell %s: %s", table_id, e)
            self.stats["errors"].append(f"Processing error {table_id}: {e!s}")

    async def run(self) -> dict:
        """Huvudprocess: scrapa och indexera alla SCB-tabeller"""
        logger.info("=== SCB SCRAPING STARTED ===")
        start_time = datetime.now()

        try:
            # Initiera
            await self.initialize()

            # Hämta alla tabeller
            tables = await self.fetch_all_tables()

            if not tables:
                logger.error("Inga tabeller hittades!")
                return self.generate_report("FLAGGAD")

            # Begränsa antal tabeller om konfigurerat
            if MAX_TABLES_LIMIT:
                tables = tables[:MAX_TABLES_LIMIT]
                logger.info("Begränsar till %d tabeller (MAX_TABLES_LIMIT)", len(tables))

            # Processera tabeller
            logger.info("Börjar processera %d tabeller...", len(tables))
            for i, table in enumerate(tables):
                logger.info(
                    "Processerar tabell %d/%d: %s", i + 1, len(tables), table.get("id", "?")
                )
                await self.process_table(table)

            # Avsluta
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("=== SCB SCRAPING COMPLETED ===")
            logger.info("Tid: %.2f sekunder", duration)
            logger.info("Tabeller funna: %d", self.stats["tables_found"])
            logger.info("Tabeller processade: %d", self.stats["tables_processed"])
            logger.info("Dokument indexerade: %d", self.stats["docs_indexed"])
            logger.info("Fel: %d", len(self.stats["errors"]))

            # Generera rapport
            status = "FLAGGAD" if self.stats["docs_indexed"] < MIN_EXPECTED_DOCS else "OK"
            return self.generate_report(status)

        except Exception as e:
            logger.error("Kritiskt fel: %s", e, exc_info=True)
            self.stats["errors"].append(f"Critical error: {e!s}")
            return self.generate_report("FLAGGAD")

        finally:
            await self.client.aclose()

    def generate_report(self, status: str) -> dict:
        """Generera slutrapport i JSON-format"""
        report = {
            "myndighet": "SCB",
            "status": status,
            "docs_found": self.stats["tables_found"],
            "docs_indexed": self.stats["docs_indexed"],
            "errors": self.stats["errors"][:20],  # Max 20 första fel
        }

        if status == "FLAGGAD":
            logger.warning(
                "⚠️  SIMON: SCB verkar ha problem - endast %d dokument indexerade (förväntat: %d+)",
                self.stats["docs_indexed"],
                MIN_EXPECTED_DOCS,
            )

        return report


async def main():
    """Main entry point"""
    scraper = SCBScraper()
    report = await scraper.run()

    # Spara rapport
    report_path = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scb_scrape_report.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Rapport sparad: %s", report_path)

    # Skriv ut rapport
    print("\n" + "=" * 60)
    print("SCB SCRAPING REPORT")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("=" * 60)

    return report


if __name__ == "__main__":
    asyncio.run(main())
