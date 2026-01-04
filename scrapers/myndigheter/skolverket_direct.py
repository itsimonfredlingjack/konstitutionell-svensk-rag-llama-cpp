#!/usr/bin/env python3
"""
SKOLVERKET DIRECT SCRAPER
=========================
Targets known static publication series pages with PDFs.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import aiohttp
import chromadb
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "skolverket"
MIN_DOC_THRESHOLD = 100

# Direct publication series URLs (these have static content)
TARGET_URLS = [
    # Styrdokument
    "https://www.skolverket.se/publikationsserier/styrdokument",
    # Allmänna råd
    "https://www.skolverket.se/publikationsserier/allmanna-rad",
    # Rapporter
    "https://www.skolverket.se/publikationsserier/rapporter",
    # Regeringsuppdrag
    "https://www.skolverket.se/publikationsserier/regeringsuppdrag",
    # Ovrigt material
    "https://www.skolverket.se/publikationsserier/ovrigt-material",
    # Statistiska analyser
    "https://www.skolverket.se/publikationsserier/statistiska-analyser",
    # Internationella studier
    "https://www.skolverket.se/publikationsserier/internationella-studier",
    # Year-based browsing (2020-2025)
    "https://www.skolverket.se/publikationsserier/styrdokument/2025",
    "https://www.skolverket.se/publikationsserier/styrdokument/2024",
    "https://www.skolverket.se/publikationsserier/styrdokument/2023",
    "https://www.skolverket.se/publikationsserier/allmanna-rad/2025",
    "https://www.skolverket.se/publikationsserier/allmanna-rad/2024",
    "https://www.skolverket.se/publikationsserier/rapporter/2025",
    "https://www.skolverket.se/publikationsserier/rapporter/2024",
    "https://www.skolverket.se/publikationsserier/rapporter/2023",
]


class DirectSkolverketScraper:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except:
            self.collection = self.client.create_collection(COLLECTION_NAME)

        self.session: Optional[aiohttp.ClientSession] = None
        self.documents: list[dict] = []
        self.stats = {
            "urls_scraped": 0,
            "pdfs_found": 0,
            "pages_found": 0,
            "new_added": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkolverketDirectScraper/1.0)"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_doc_id(self, url: str, title: str) -> str:
        return hashlib.sha256(f"{url}|{title}".encode()).hexdigest()

    def _exists_in_db(self, doc_id: str) -> bool:
        try:
            return len(self.collection.get(ids=[doc_id])["ids"]) > 0
        except:
            return False

    async def fetch(self, url: str) -> Optional[str]:
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.debug(f"HTTP {response.status}: {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def scrape_url(self, url: str):
        """Scrape a single URL for PDFs and publication links"""
        logger.info(f"Scraping: {url}")
        html = await self.fetch(url)
        if not html:
            return

        self.stats["urls_scraped"] += 1
        soup = BeautifulSoup(html, "lxml")

        # Find all links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)
            text = a.get_text(strip=True)

            # PDF files
            if href.endswith(".pdf"):
                title = text or Path(href).name
                doc_id = self._generate_doc_id(full_url, title)

                if not self._exists_in_db(doc_id):
                    category = "publikation"
                    if "styrdokument" in url:
                        category = "laroplan"
                    elif "allmanna-rad" in url:
                        category = "allmanna_rad"
                    elif "rapport" in url:
                        category = "rapport"

                    self.documents.append(
                        {
                            "id": doc_id,
                            "url": full_url,
                            "title": title,
                            "category": category,
                            "type": "pdf",
                            "content": f"PDF: {title}\nURL: {full_url}",
                        }
                    )
                    self.stats["pdfs_found"] += 1
                    logger.info(f"  📄 PDF: {title}")

            # Publication detail pages
            elif "/publikationsserier/" in href and not href.endswith((".pdf", ".jpg", ".png")):
                # This is a publication detail page - fetch it
                await self.scrape_publication_page(full_url)

    async def scrape_publication_page(self, url: str):
        """Scrape individual publication page"""
        # Avoid re-scraping seed URLs
        if url in TARGET_URLS:
            return

        html = await self.fetch(url)
        if not html:
            return

        soup = BeautifulSoup(html, "lxml")

        # Extract PDFs from this page
        for a in soup.find_all("a", href=True):
            if a["href"].endswith(".pdf"):
                pdf_url = urljoin(url, a["href"])
                title_tag = soup.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)

                doc_id = self._generate_doc_id(pdf_url, title)

                if not self._exists_in_db(doc_id):
                    category = "publikation"
                    if "styrdokument" in url:
                        category = "laroplan"
                    elif "allmanna-rad" in url:
                        category = "allmanna_rad"
                    elif "rapport" in url:
                        category = "rapport"

                    self.documents.append(
                        {
                            "id": doc_id,
                            "url": pdf_url,
                            "title": title,
                            "category": category,
                            "type": "pdf",
                            "content": f"Publikation: {title}\nURL: {pdf_url}\nKälla: {url}",
                        }
                    )
                    self.stats["pdfs_found"] += 1
                    logger.info(f"  📄 PDF: {title}")
                    break  # Usually only one main PDF per publication

        # Also save page content
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if main:
            for tag in main(["script", "style", "nav", "footer"]):
                tag.decompose()

            content = main.get_text(separator="\n", strip=True)
            content = re.sub(r"\n{3,}", "\n\n", content)

            if len(content) > 200:
                title_tag = soup.find("h1")
                page_title = (
                    title_tag.get_text(strip=True) if title_tag else "Skolverket Publikation"
                )

                doc_id = self._generate_doc_id(url, page_title)

                if not self._exists_in_db(doc_id):
                    self.documents.append(
                        {
                            "id": doc_id,
                            "url": url,
                            "title": page_title,
                            "category": "publikation",
                            "type": "webpage",
                            "content": content,
                        }
                    )
                    self.stats["pages_found"] += 1

        await asyncio.sleep(0.5)  # Rate limiting

    def store_documents(self):
        if not self.documents:
            return

        ids = [d["id"] for d in self.documents]
        texts = [d["content"] for d in self.documents]
        metadatas = [
            {
                "source": SOURCE_NAME,
                "url": d["url"],
                "title": d["title"],
                "category": d["category"],
                "type": d["type"],
                "scraped_at": datetime.now().isoformat(),
            }
            for d in self.documents
        ]

        try:
            self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
            self.stats["new_added"] = len(self.documents)
            logger.info(f"Stored {len(self.documents)} documents")
        except Exception as e:
            logger.error(f"Error storing documents: {e}")
            self.stats["errors"] += 1

    async def run(self):
        logger.info("=" * 60)
        logger.info("SKOLVERKET DIRECT SCRAPER")
        logger.info("=" * 60)

        for url in TARGET_URLS:
            await self.scrape_url(url)
            await asyncio.sleep(1)

        self.store_documents()

        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"URLs scraped: {self.stats['urls_scraped']}")
        logger.info(f"PDFs found: {self.stats['pdfs_found']}")
        logger.info(f"Pages found: {self.stats['pages_found']}")
        logger.info(f"New documents added: {self.stats['new_added']}")
        logger.info(f"Errors: {self.stats['errors']}")

        if self.stats["new_added"] < MIN_DOC_THRESHOLD:
            logger.warning(
                f"\n⚠️  WARNING: Only {self.stats['new_added']} documents (threshold: {MIN_DOC_THRESHOLD})"
            )
        else:
            logger.info(f"\n✓ Success: {self.stats['new_added']} documents")

        return self.stats


async def main():
    async with DirectSkolverketScraper() as scraper:
        stats = await scraper.run()

        report = {
            "timestamp": datetime.now().isoformat(),
            "source": SOURCE_NAME,
            "method": "direct_series_scrape",
            "stats": stats,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "threshold_met": stats["new_added"] >= MIN_DOC_THRESHOLD,
        }

        report_path = Path(__file__).parent / "skolverket_direct_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n📄 Report: {report_path}")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
