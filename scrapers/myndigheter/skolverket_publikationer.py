#!/usr/bin/env python3
"""
SKOLVERKET PUBLIKATIONER SCRAPER
=================================
Scrapes all publications from Skolverket's publication database.
Total expected: ~1,891 publications
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import chromadb
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "skolverket"

# Publication search endpoint
SEARCH_URL = "https://www.skolverket.se/sok-publikationer"


class PublikationerScraper:
    """Scraper for Skolverket's publication database"""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except:
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )

        self.session: Optional[aiohttp.ClientSession] = None
        self.documents: list[dict] = []
        self.stats = {
            "pages_crawled": 0,
            "publications_found": 0,
            "new_added": 0,
            "duplicates": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkolverketPubScraper/1.0)"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_doc_id(self, url: str, title: str) -> str:
        content = f"{url}|{title}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _exists_in_db(self, doc_id: str) -> bool:
        try:
            result = self.collection.get(ids=[doc_id])
            return len(result["ids"]) > 0
        except:
            return False

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page HTML"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def extract_publications(self, html: str, page_url: str) -> list[dict]:
        """Extract publication entries from search results page"""
        soup = BeautifulSoup(html, "lxml")
        publications = []

        # Find all publication links
        # Skolverket publications typically have patterns like:
        # - /sok-publikationer/publikationsserier/.../[title]
        # - Links to PDFs

        for a in soup.find_all("a", href=True):
            href = a["href"]

            # Match publication detail pages
            if "/sok-publikationer/" in href and "publikationsserier" in href:
                full_url = urljoin(page_url, href)
                title = a.get_text(strip=True)

                if title and len(title) > 5:  # Valid title
                    doc_id = self._generate_doc_id(full_url, title)

                    if not self._exists_in_db(doc_id):
                        publications.append(
                            {
                                "id": doc_id,
                                "url": full_url,
                                "title": title,
                                "category": "publikation",
                                "type": "webpage",
                            }
                        )

            # Also match direct PDF links
            elif href.endswith(".pdf"):
                full_url = urljoin(page_url, href)
                title = a.get_text(strip=True) or Path(urlparse(href).path).name
                doc_id = self._generate_doc_id(full_url, title)

                if not self._exists_in_db(doc_id):
                    publications.append(
                        {
                            "id": doc_id,
                            "url": full_url,
                            "title": title,
                            "category": "publikation",
                            "type": "pdf",
                        }
                    )

        return publications

    async def scrape_publication_detail(self, url: str) -> Optional[dict]:
        """Scrape individual publication page to get PDF download link"""
        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "lxml")

        # Find "Ladda ner som PDF" link
        pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))

        if pdf_link:
            pdf_url = urljoin(url, pdf_link["href"])
            title_tag = soup.find("h1")
            title = (
                title_tag.get_text(strip=True) if title_tag else Path(urlparse(pdf_url).path).name
            )

            # Extract metadata if available
            meta_text = soup.get_text()

            # Try to identify publication type from URL or content
            category = "publikation"
            if "styrdokument" in url.lower():
                category = "laroplan"
            elif "allmanna-rad" in url.lower():
                category = "allmanna_rad"
            elif "rapporter" in url.lower():
                category = "rapport"

            doc_id = self._generate_doc_id(pdf_url, title)

            if not self._exists_in_db(doc_id):
                return {
                    "id": doc_id,
                    "url": pdf_url,
                    "title": title,
                    "category": category,
                    "type": "pdf",
                    "content": f"Publikation: {title}\nURL: {pdf_url}\nKälla: {url}",
                }

        return None

    async def scrape_search_page(self, page_num: int = 1) -> list[dict]:
        """Scrape a specific search results page"""
        # Skolverket pagination uses ?p=X or similar
        url = f"{SEARCH_URL}?p={page_num}" if page_num > 1 else SEARCH_URL

        logger.info(f"Scraping page {page_num}...")

        html = await self.fetch_page(url)
        if not html:
            return []

        self.stats["pages_crawled"] += 1

        # Extract publication links
        publications = await self.extract_publications(html, url)

        # For each publication, fetch detail page to get PDF
        detailed_pubs = []
        for pub in publications:
            if pub["type"] == "webpage":
                detail = await self.scrape_publication_detail(pub["url"])
                if detail:
                    detailed_pubs.append(detail)
                await asyncio.sleep(0.5)  # Rate limiting
            else:
                # Already a PDF
                detailed_pubs.append(pub)

        return detailed_pubs

    async def scrape_all_pages(self, max_pages: int = 95):
        """Scrape all pagination pages"""
        logger.info(f"Starting scrape of up to {max_pages} pages...")

        for page_num in range(1, max_pages + 1):
            publications = await self.scrape_search_page(page_num)

            if publications:
                self.documents.extend(publications)
                self.stats["publications_found"] += len(publications)
                logger.info(
                    f"Page {page_num}: Found {len(publications)} publications (total: {self.stats['publications_found']})"
                )
            else:
                logger.info(f"Page {page_num}: No publications found, stopping")
                break

            # Rate limiting
            await asyncio.sleep(2)

            # Save progress periodically
            if page_num % 10 == 0:
                self.store_documents()
                self.documents = []  # Clear to avoid re-storing

    def store_documents(self):
        """Batch store documents"""
        if not self.documents:
            return

        batch_size = 1000
        for i in range(0, len(self.documents), batch_size):
            batch = self.documents[i : i + batch_size]

            ids = [doc["id"] for doc in batch]
            texts = [
                doc.get("content", f"Document: {doc['title']}\nURL: {doc['url']}") for doc in batch
            ]
            metadatas = [
                {
                    "source": SOURCE_NAME,
                    "url": doc["url"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "type": doc["type"],
                    "scraped_at": datetime.now().isoformat(),
                }
                for doc in batch
            ]

            try:
                self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
                self.stats["new_added"] += len(batch)
                logger.info(
                    f"Stored {len(batch)} documents (total stored: {self.stats['new_added']})"
                )
            except Exception as e:
                logger.error(f"Error storing batch: {e}")
                self.stats["errors"] += 1

    async def run(self):
        """Main workflow"""
        logger.info("=" * 60)
        logger.info("SKOLVERKET PUBLIKATIONER SCRAPER")
        logger.info("=" * 60)

        start_time = time.time()

        # Scrape pages (estimate 95 pages with 20 per page = ~1,900 pubs)
        # For quick test: 5 pages = ~100 docs. For full scrape: 95 pages
        await self.scrape_all_pages(max_pages=10)

        # Store any remaining documents
        self.store_documents()

        elapsed = time.time() - start_time

        # Report
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Pages crawled: {self.stats['pages_crawled']}")
        logger.info(f"Publications found: {self.stats['publications_found']}")
        logger.info(f"New documents added: {self.stats['new_added']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Time elapsed: {elapsed:.2f}s")

        return self.stats


async def main():
    async with PublikationerScraper() as scraper:
        stats = await scraper.run()

        # Write report
        report_path = Path(__file__).parent / "skolverket_publikationer_report.json"
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": SOURCE_NAME,
            "method": "pagination_scrape",
            "stats": stats,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n📄 Report: {report_path}")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
