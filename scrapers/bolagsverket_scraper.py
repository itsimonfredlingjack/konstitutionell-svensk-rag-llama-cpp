#!/usr/bin/env python3
"""
BOLAGSVERKET SCRAPER - OPERATION MYNDIGHETS-SWEEP
Scrapes Bolagsverket documents: BOLFS, vägledningar, blanketter, rapporter
Uses multiple sources: bolagsverket.se and lagen.nu
"""

import asyncio
import hashlib
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import chromadb
import httpx
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential

# Konfiguration
BOLAGSVERKET_BASE = "https://www.bolagsverket.se"
LAGEN_NU_BASE = "https://lagen.nu"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # 384 dims - matches collection
)
RATE_LIMIT_DELAY = 2.0  # Respektfull rate limiting
MIN_EXPECTED_DOCS = 100  # Flagga om färre än detta
MAX_RETRY_ATTEMPTS = 3

# Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Bolagsverket_Scraper")


class BolagsverketScraper:
    """Multi-source scraper för Bolagsverket dokument"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
            timeout=60.0,
            follow_redirects=True,
        )
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.stats = {
            "bolfs_found": 0,
            "reports_found": 0,
            "guides_found": 0,
            "docs_indexed": 0,
            "pdf_extracted": 0,
            "errors": [],
        }
        self.seen_urls = set()

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

    @retry(
        wait=wait_exponential(min=2, max=60),
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        reraise=True,
    )
    async def _fetch_content(self, url: str) -> bytes | None:
        """Hämta innehåll från URL med retry"""
        try:
            response = await self.client.get(url)

            # Check if we hit CAPTCHA
            if b"support ID" in response.content and b"image" in response.content.lower():
                logger.warning("CAPTCHA detected at %s, skipping", url)
                self.stats["errors"].append(f"CAPTCHA: {url}")
                return None

            response.raise_for_status()
            await asyncio.sleep(RATE_LIMIT_DELAY)
            return response.content

        except httpx.HTTPError as e:
            logger.error("HTTP error för %s: %s", url, e)
            self.stats["errors"].append(f"HTTP error: {url} - {e!s}")
            return None

    async def extract_pdf_text(self, pdf_content: bytes) -> str:
        """Extrahera text från PDF - försök med både PyPDF2 och pdfplumber"""
        # Try PyPDF2 first
        try:
            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file, strict=False)

            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            if text_parts:
                full_text = "\n".join(text_parts)
                self.stats["pdf_extracted"] += 1
                return full_text

        except Exception as e:
            logger.debug("PyPDF2 failed: %s", e)

        # Try pdfplumber as fallback
        try:
            import pdfplumber

            pdf_file = io.BytesIO(pdf_content)
            text_parts = []

            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            if text_parts:
                full_text = "\n".join(text_parts)
                self.stats["pdf_extracted"] += 1
                return full_text

        except ImportError:
            logger.debug("pdfplumber not installed, skipping")
        except Exception as e:
            logger.error("Fel vid PDF-extraktion (både PyPDF2 och pdfplumber): %s", e)
            self.stats["errors"].append(f"PDF extraction error: {e!s}")

        return ""

    def generate_doc_id(self, source: str, identifier: str) -> str:
        """Generera unikt dokument-ID"""
        combined = f"{source}_{identifier}"
        hash_suffix = hashlib.sha256(combined.encode()).hexdigest()[:8]
        return f"bolagsverket_{source}_{hash_suffix}"

    async def scrape_lagen_nu_bolfs(self) -> list[dict]:
        """Scrapa BOLFS från lagen.nu (ingen CAPTCHA)"""
        logger.info("Scraping BOLFS från lagen.nu...")
        docs = []

        # Hämta index-sidan
        index_url = f"{LAGEN_NU_BASE}/dataset/myndfs?rpubl_forfattningssamling=bolfs"
        content = await self._fetch_content(index_url)

        if not content:
            return docs

        soup = BeautifulSoup(content, "html.parser")

        # Hitta alla BOLFS-länkar
        bolfs_pattern = re.compile(r"/bolfs/\d{4}:\d+")
        links = soup.find_all("a", href=bolfs_pattern)

        logger.info("Hittade %d BOLFS-dokument på lagen.nu", len(links))

        for link in links:
            href = link.get("href")
            full_url = urljoin(LAGEN_NU_BASE, href)

            if full_url in self.seen_urls:
                continue

            self.seen_urls.add(full_url)

            # Extrahera BOLFS-nummer
            match = re.search(r"bolfs/(\d{4}:\d+)", href)
            if not match:
                continue

            bolfs_id = match.group(1)

            # Hämta dokument-sidan
            doc_content = await self._fetch_content(full_url)
            if not doc_content:
                continue

            doc_soup = BeautifulSoup(doc_content, "html.parser")

            # Extrahera text och metadata
            title = doc_soup.find("h1")
            title_text = title.get_text(strip=True) if title else f"BOLFS {bolfs_id}"

            # Hämta textinnehåll - extrahera från hela article
            article_tag = doc_soup.find("article")
            if article_tag:
                full_text = article_tag.get_text(separator="\n", strip=True)
            else:
                # Fallback: försök hitta main content
                content_div = doc_soup.find("div", {"class": "forfattning"})
                if content_div:
                    full_text = content_div.get_text(separator="\n", strip=True)
                else:
                    # Last resort: get all text
                    full_text = doc_soup.get_text(separator="\n", strip=True)

            docs.append(
                {
                    "id": bolfs_id,
                    "title": title_text,
                    "text": full_text,
                    "url": full_url,
                    "source": "lagen.nu",
                    "type": "BOLFS",
                }
            )

            self.stats["bolfs_found"] += 1
            logger.info("Scraped BOLFS %s: %s", bolfs_id, title_text)

        return docs

    async def scrape_known_bolfs_pdfs(self) -> list[dict]:
        """Scrapa kända BOLFS PDF:er från bolagsverket.se"""
        logger.info("Scraping known BOLFS PDFs from bolagsverket.se...")
        docs = []

        # Kända BOLFS PDF-URLer från web search
        known_pdfs = [
            "https://www.bolagsverket.se/download/18.5480e1ea1848204e4241e4/1669792089493/bolfs-2022-1.pdf",
            "https://www.bolagsverket.se/download/18.6535432417e0f20712756ea1/1643114949506/2019-1.pdf",
            "https://bolagsverket.se/download/18.6535432417e0f20712756ea6/1643114954151/bolfs_2008_1.pdf",
            "https://bolagsverket.se/download/18.46f4138717c599ee403aafdd/1638951747512/bolfs_2009_1.pdf",
            "https://www.bolagsverket.se/polopoly_fs/1.2412!/Menu/general/column-content/file/bolfs_2007_1.pdf",
            "https://www.bolagsverket.se/polopoly_fs/1.12781!/foreskrift-elektronisk-ansokan-anmalan-vissa-foretag.pdf",
        ]

        for pdf_url in known_pdfs:
            if pdf_url in self.seen_urls:
                continue

            self.seen_urls.add(pdf_url)

            # Extract BOLFS ID from URL
            match = re.search(r"(\d{4})[_-](\d+)", pdf_url)
            if match:
                bolfs_id = f"{match.group(1)}:{match.group(2)}"
            else:
                bolfs_id = pdf_url.split("/")[-1].replace(".pdf", "")

            logger.info("Hämtar PDF: %s", pdf_url)
            pdf_content = await self._fetch_content(pdf_url)

            if not pdf_content:
                continue

            # Extrahera text från PDF
            text = await self.extract_pdf_text(pdf_content)

            if not text or len(text) < 100:
                logger.warning("Tom eller mycket kort PDF: %s", pdf_url)
                continue

            docs.append(
                {
                    "id": bolfs_id,
                    "title": f"BOLFS {bolfs_id}",
                    "text": text,
                    "url": pdf_url,
                    "source": "bolagsverket.se",
                    "type": "BOLFS_PDF",
                }
            )

            self.stats["bolfs_found"] += 1
            logger.info("Extracted PDF BOLFS %s (%d chars)", bolfs_id, len(text))

        return docs

    async def search_bolagsverket_download_pattern(self) -> list[dict]:
        """Försök hitta fler dokument via download-pattern matching"""
        logger.info("Searching for documents via URL patterns...")
        docs = []

        # Test common ID patterns
        test_patterns = [
            # BOLFS patterns
            ("bolfs", range(2004, 2024), range(1, 5)),  # 2004-2023, nr 1-4
            # Reports
            ("rapport", range(2020, 2024), range(1, 10)),
        ]

        for doc_type, years, numbers in test_patterns:
            for year in years:
                for num in numbers:
                    # Test various URL patterns
                    test_urls = [
                        f"{BOLAGSVERKET_BASE}/download/18.xxx/{doc_type}_{year}_{num}.pdf",
                        f"{BOLAGSVERKET_BASE}/download/{doc_type}-{year}-{num}.pdf",
                    ]

                    for url in test_urls:
                        # Skip if would just fail - this is a heuristic search
                        if url in self.seen_urls:
                            continue

                        # Only try a subset to avoid hammering
                        if len(docs) > 50:  # Limit pattern matching
                            break

                        # Note: Actual implementation would need valid hash IDs
                        # Skipping for now as we don't have the hash pattern
                        break

        return docs

    async def index_document(self, doc: dict):
        """Indexera ett dokument till ChromaDB"""
        try:
            doc_id = self.generate_doc_id(doc["type"], doc["id"])
            text_content = f"{doc['title']}\n\n{doc['text']}"

            if not text_content.strip() or len(text_content) < 100:
                logger.warning("För kort textinnehåll för %s, hoppar över", doc["id"])
                return

            # Generera embedding
            embedding = self.embedding_model.encode(text_content).tolist()

            # Metadata för ChromaDB
            chroma_metadata = {
                "source": "bolagsverket",
                "doc_type": doc["type"],
                "doc_id": doc["id"],
                "title": doc["title"][:500],  # ChromaDB metadata limit
                "url": doc["url"],
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

            if self.stats["docs_indexed"] % 10 == 0:
                logger.info("Indexerat %d dokument...", self.stats["docs_indexed"])

        except Exception as e:
            logger.error("Fel vid indexering av %s: %s", doc.get("id", "?"), e)
            self.stats["errors"].append(f"Indexing error {doc.get('id', '?')}: {e!s}")

    async def run(self) -> dict:
        """Huvudprocess: scrapa och indexera Bolagsverket-dokument"""
        logger.info("=== BOLAGSVERKET SCRAPING STARTED ===")
        start_time = datetime.now()

        try:
            # Initiera
            await self.initialize()

            all_docs = []

            # Scrapa från olika källor
            logger.info("Source 1: lagen.nu BOLFS...")
            lagen_nu_docs = await self.scrape_lagen_nu_bolfs()
            all_docs.extend(lagen_nu_docs)

            logger.info("Source 2: Known BOLFS PDFs...")
            pdf_docs = await self.scrape_known_bolfs_pdfs()
            all_docs.extend(pdf_docs)

            # Indexera alla dokument
            logger.info("Indexerar %d dokument...", len(all_docs))
            for doc in all_docs:
                await self.index_document(doc)

            # Avsluta
            duration = (datetime.now() - start_time).total_seconds()
            logger.info("=== BOLAGSVERKET SCRAPING COMPLETED ===")
            logger.info("Tid: %.2f sekunder", duration)
            logger.info("BOLFS funna: %d", self.stats["bolfs_found"])
            logger.info("Dokument indexerade: %d", self.stats["docs_indexed"])
            logger.info("PDF:er extraherade: %d", self.stats["pdf_extracted"])
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
            "myndighet": "Bolagsverket",
            "status": status,
            "bolfs_found": self.stats["bolfs_found"],
            "docs_indexed": self.stats["docs_indexed"],
            "pdf_extracted": self.stats["pdf_extracted"],
            "errors": self.stats["errors"][:20],
            "breakdown": {
                "bolfs": self.stats["bolfs_found"],
                "reports": self.stats["reports_found"],
                "guides": self.stats["guides_found"],
            },
        }

        if status == "FLAGGAD":
            logger.warning(
                "⚠️  FLAGGAD: Bolagsverket - endast %d dokument indexerade (förväntat: %d+)",
                self.stats["docs_indexed"],
                MIN_EXPECTED_DOCS,
            )

        return report


async def main():
    """Main entry point"""
    scraper = BolagsverketScraper()
    report = await scraper.run()

    # Spara rapport
    report_path = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/bolagsverket_scrape_report.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Rapport sparad: %s", report_path)

    # Skriv ut rapport
    print("\n" + "=" * 60)
    print("BOLAGSVERKET SCRAPING REPORT")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("=" * 60)

    return report


if __name__ == "__main__":
    asyncio.run(main())
