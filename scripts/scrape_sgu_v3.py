#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - SGU (Sveriges geologiska undersökning) V3

Strategy:
1. Scrape publication listing pages
2. Extract PDF links (both direct PDFs and webpage content)
3. Download and extract text from PDFs using PyPDF2
4. Extract webpage content where no PDF exists
5. Store all in ChromaDB with source="sgu"
"""

import asyncio
import hashlib
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import aiohttp
import chromadb
from bs4 import BeautifulSoup

# Try importing PyPDF2, fall back to basic text extraction
try:
    from PyPDF2 import PdfReader

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False
    logging.warning("PyPDF2 not available - PDF extraction will be limited")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
BASE_URL = "https://www.sgu.se"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 10
PDF_MAX_SIZE = 10 * 1024 * 1024  # 10MB

# Listing pages
SEED_URLS = [
    # Nypublicerat pages (chronological listings)
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2024/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2023/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2022/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2021/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2020/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2019/",
    # Föreskrifter
    "https://www.sgu.se/om-sgu/verksamhet/foreskrifter/",
    # Periodiska publikationer
    "https://www.sgu.se/mineralnaring/mineralstatistik/mineralmarknaden-rapportserie/",
    "https://www.sgu.se/mineralnaring/mineralstatistik/bergverksstatistik/",
]


class SGUScraperV3:
    """PDF-enabled scraper for SGU"""

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Swedish government documents from multiple sources"},
        )
        self.scraped_urls: set[str] = set()
        self.documents: list[dict] = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.pdf_semaphore = asyncio.Semaphore(3)  # Limit PDF downloads

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def generate_doc_id(self, url: str, title: str) -> str:
        """Generate unique document ID"""
        content = f"{url}|{title}".encode()
        return hashlib.sha256(content).hexdigest()[:16]

    async def fetch_page(self, url: str) -> str | None:
        """Fetch page content"""
        async with self.semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
            except Exception as e:
                logger.debug(f"Error fetching {url}: {e}")
                return None

    async def fetch_pdf(self, url: str) -> bytes | None:
        """Fetch PDF content"""
        async with self.pdf_semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status != 200:
                        return None

                    # Check size
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > PDF_MAX_SIZE:
                        logger.debug(f"PDF too large: {url}")
                        return None

                    return await response.read()
            except Exception as e:
                logger.debug(f"Error fetching PDF {url}: {e}")
                return None

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str | None:
        """Extract text from PDF bytes"""
        if not HAS_PYPDF:
            return None

        try:
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            text_parts = []
            # Extract from first 20 pages max
            max_pages = min(20, len(reader.pages))

            for i in range(max_pages):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception as e:
                    logger.debug(f"Error extracting page {i}: {e}")
                    continue

            full_text = "\n".join(text_parts)

            # Clean up text
            full_text = re.sub(r"\s+", " ", full_text)
            full_text = full_text.strip()

            return full_text if len(full_text) > 200 else None

        except Exception as e:
            logger.debug(f"Error processing PDF: {e}")
            return None

    async def process_pdf_link(self, url: str, title: str, year: str = "unknown") -> dict | None:
        """Download and process a PDF document"""
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)

        # Fetch PDF
        pdf_bytes = await self.fetch_pdf(url)
        if not pdf_bytes:
            return None

        # Extract text
        text = self.extract_text_from_pdf(pdf_bytes)
        if not text or len(text) < 200:
            logger.debug(f"Insufficient text extracted from {url}")
            return None

        # Determine doc type
        doc_type = "rapport"
        title_lower = title.lower()
        url_lower = url.lower()

        if "foreskrift" in title_lower or "sgu-fs" in title_lower:
            doc_type = "föreskrift"
        elif (
            "periodisk" in title_lower
            or "bergverksstatistik" in url_lower
            or "mineralmarknaden" in url_lower
        ):
            doc_type = "periodisk_publikation"
        elif "karta" in title_lower:
            doc_type = "karta"

        logger.info(f"✓ PDF: {title[:60]}... ({len(text)} chars)")

        return {
            "title": title,
            "content": text[:50000],  # Limit content size
            "url": url,
            "doc_type": doc_type,
            "publication_date": year,
            "source": "sgu",
            "format": "pdf",
            "scraped_at": datetime.now().isoformat(),
        }

    async def extract_pdf_links_from_page(self, page_url: str) -> list[dict[str, str]]:
        """Extract all PDF links from a listing page"""
        html = await self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        pdf_links = []

        # Find all links
        for a in soup.find_all("a", href=True):
            href = a["href"]

            # Make absolute
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"
            elif not href.startswith("http"):
                continue

            # Only PDFs
            if not href.lower().endswith(".pdf"):
                continue

            # Extract title
            title = a.get_text(strip=True)
            if not title:
                # Try parent element
                parent = a.parent
                if parent:
                    title = parent.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            # Extract year from title or URL
            year = "unknown"
            year_match = re.search(r"(\d{4})", title)
            if not year_match:
                year_match = re.search(r"(\d{4})", href)
            if year_match:
                year = year_match.group(1)

            pdf_links.append({"url": href, "title": title, "year": year})

        return pdf_links

    async def run(self):
        """Main scraping logic"""
        logger.info("=" * 60)
        logger.info("OPERATION MYNDIGHETS-SWEEP - SGU V3 (PDF-enabled)")
        logger.info("=" * 60)

        if not HAS_PYPDF:
            logger.warning("PyPDF2 not available - installing...")
            import subprocess

            subprocess.run(["pip3", "install", "PyPDF2"], check=False)

        # Phase 1: Discover PDF links
        logger.info("\nPhase 1: Discovering PDF links...")

        all_pdf_links = []

        for seed_url in SEED_URLS:
            logger.info(f"Scanning: {seed_url}")
            pdf_links = await self.extract_pdf_links_from_page(seed_url)
            all_pdf_links.extend(pdf_links)
            logger.info(f"  Found {len(pdf_links)} PDFs")
            await asyncio.sleep(0.5)

        logger.info(f"\nTotal PDF links discovered: {len(all_pdf_links)}")

        # Phase 2: Process PDFs
        logger.info("\nPhase 2: Downloading and processing PDFs...")

        tasks = []
        processed = 0

        for pdf_link in all_pdf_links:
            task = self.process_pdf_link(pdf_link["url"], pdf_link["title"], pdf_link["year"])
            tasks.append(task)

            # Process in batches
            if len(tasks) >= 20:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                        processed += 1

                tasks = []
                logger.info(
                    f"Progress: {processed}/{len(all_pdf_links)} PDFs processed, {len(self.documents)} documents extracted"
                )

        # Process remaining
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Phase 3: Save to JSON (ChromaDB has issues)
        logger.info(f"\nPhase 3: Saving {len(self.documents)} documents to JSON...")

        if self.documents:
            # Save all documents to JSON
            json_path = Path(__file__).parent / "sgu_documents.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved to: {json_path}")
            logger.info("Run separate script to import into ChromaDB")

        # Generate report
        report = self.generate_report()
        return report

    def generate_report(self) -> dict:
        """Generate final report"""
        total_docs = len(self.documents)

        # Count by type
        type_counts = {}
        year_counts = {}

        for doc in self.documents:
            doc_type = doc["doc_type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

            year = doc.get("publication_date", "unknown")
            year_counts[year] = year_counts.get(year, 0) + 1

        # Check threshold
        status = (
            "✓ SUCCESS"
            if total_docs >= MIN_DOCS_THRESHOLD
            else f"⚠ WARNING: Only {total_docs} docs (< {MIN_DOCS_THRESHOLD})"
        )

        report = {
            "agency": "SGU",
            "source": "sgu",
            "total_documents": total_docs,
            "document_types": type_counts,
            "years": dict(sorted(year_counts.items(), reverse=True)[:10]),  # Top 10 years
            "status": status,
            "threshold": MIN_DOCS_THRESHOLD,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "timestamp": datetime.now().isoformat(),
        }

        return report


async def main():
    """Entry point"""
    async with SGUScraperV3() as scraper:
        report = await scraper.run()

        # Print report
        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))

        # Save report
        report_path = Path(__file__).parent / "sgu_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\nReport saved: {report_path}")

        # Print warning if below threshold
        if report["total_documents"] < MIN_DOCS_THRESHOLD:
            print(f"\n{'=' * 60}")
            print(f"⚠  WARNING: Only {report['total_documents']} documents scraped!")
            print(f"   Threshold: {MIN_DOCS_THRESHOLD}")
            print(f"{'=' * 60}")
        else:
            print(f"\n{'=' * 60}")
            print(f"✓ SUCCESS: {report['total_documents']} documents scraped!")
            print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
