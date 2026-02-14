#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - SGU (FINAL VERSION)

Simple PDF scraper - no ChromaDB interaction during scraping.
Saves to JSON for later import.
"""

import asyncio
import io
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

try:
    from PyPDF2 import PdfReader

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://www.sgu.se"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 10
PDF_MAX_SIZE = 10 * 1024 * 1024  # 10MB

SEED_URLS = [
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2024/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2023/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2022/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2021/",
    "https://www.sgu.se/om-sgu/verksamhet/foreskrifter/",
    "https://www.sgu.se/mineralnaring/mineralstatistik/mineralmarknaden-rapportserie/",
]


class SGUScraperFinal:
    """Simple PDF scraper"""

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.scraped_urls: set[str] = set()
        self.documents: list[dict] = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.pdf_semaphore = asyncio.Semaphore(3)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_page(self, url: str) -> str | None:
        async with self.semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
            except Exception:
                pass
        return None

    async def fetch_pdf(self, url: str) -> bytes | None:
        async with self.pdf_semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status != 200:
                        return None
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > PDF_MAX_SIZE:
                        return None
                    return await response.read()
            except Exception:
                pass
        return None

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str | None:
        if not HAS_PYPDF:
            return None

        try:
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)
            text_parts = []
            max_pages = min(20, len(reader.pages))

            for i in range(max_pages):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                except Exception:
                    continue

            full_text = "\n".join(text_parts)
            full_text = re.sub(r"\s+", " ", full_text).strip()

            return full_text if len(full_text) > 200 else None
        except Exception:
            return None

    async def process_pdf_link(self, url: str, title: str, year: str = "unknown") -> dict | None:
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)
        pdf_bytes = await self.fetch_pdf(url)
        if not pdf_bytes:
            return None

        text = self.extract_text_from_pdf(pdf_bytes)
        if not text or len(text) < 200:
            return None

        doc_type = "rapport"
        title_lower = title.lower()

        if "foreskrift" in title_lower or "sgu-fs" in title_lower:
            doc_type = "föreskrift"
        elif "periodisk" in title_lower or "mineral" in title_lower:
            doc_type = "periodisk_publikation"
        elif "karta" in title_lower:
            doc_type = "karta"

        logger.info(f"✓ {title[:50]}...")

        return {
            "title": title,
            "content": text[:50000],
            "url": url,
            "doc_type": doc_type,
            "publication_date": year,
            "source": "sgu",
            "format": "pdf",
            "scraped_at": datetime.now().isoformat(),
        }

    async def extract_pdf_links_from_page(self, page_url: str) -> list[dict[str, str]]:
        html = await self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        pdf_links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if href.startswith("/"):
                href = f"{BASE_URL}{href}"
            elif not href.startswith("http"):
                continue

            if not href.lower().endswith(".pdf"):
                continue

            title = a.get_text(strip=True)
            if not title:
                parent = a.parent
                if parent:
                    title = parent.get_text(strip=True)

            if not title or len(title) < 10:
                continue

            year = "unknown"
            year_match = re.search(r"(\d{4})", title) or re.search(r"(\d{4})", href)
            if year_match:
                year = year_match.group(1)

            pdf_links.append({"url": href, "title": title, "year": year})

        return pdf_links

    async def run(self):
        logger.info("=" * 60)
        logger.info("SGU SCRAPER FINAL")
        logger.info("=" * 60)

        # Phase 1: Discover PDFs
        logger.info("\nDiscovering PDF links...")
        all_pdf_links = []

        for seed_url in SEED_URLS:
            logger.info(f"Scanning: {seed_url}")
            pdf_links = await self.extract_pdf_links_from_page(seed_url)
            all_pdf_links.extend(pdf_links)
            logger.info(f"  Found {len(pdf_links)} PDFs")
            await asyncio.sleep(0.5)

        logger.info(f"\nTotal: {len(all_pdf_links)} PDFs")

        # Phase 2: Process PDFs
        logger.info("\nProcessing PDFs...")
        tasks = []

        for pdf_link in all_pdf_links:
            tasks.append(
                self.process_pdf_link(pdf_link["url"], pdf_link["title"], pdf_link["year"])
            )

            if len(tasks) >= 20:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                tasks = []
                logger.info(f"Progress: {len(self.documents)} documents")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Save to JSON
        logger.info(f"\nSaving {len(self.documents)} documents...")

        if self.documents:
            json_path = Path(__file__).parent / "sgu_documents.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(self.documents, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved: {json_path}")

        # Generate report
        type_counts = {}
        for doc in self.documents:
            doc_type = doc["doc_type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        status = (
            "✓ SUCCESS"
            if len(self.documents) >= MIN_DOCS_THRESHOLD
            else f"⚠ WARNING: Only {len(self.documents)} docs"
        )

        report = {
            "agency": "SGU",
            "source": "sgu",
            "total_documents": len(self.documents),
            "document_types": type_counts,
            "status": status,
            "threshold": MIN_DOCS_THRESHOLD,
            "timestamp": datetime.now().isoformat(),
        }

        report_path = Path(__file__).parent / "sgu_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"\nDocuments saved: {json_path}")
        print(f"Report saved: {report_path}")

        return report


async def main():
    async with SGUScraperFinal() as scraper:
        await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
