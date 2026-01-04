#!/usr/bin/env python3
"""
SKOLVERKET DEEP SCRAPER
=======================
Aggressive deep-link scraper for Skolverket documents.
Uses recursive crawling to find all PDFs and documents.
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
from urllib.parse import urljoin, urlparse, urlunparse

import aiohttp
import chromadb
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "skolverket"
MIN_DOC_THRESHOLD = 100

# Starting URLs for deep crawl
SEED_URLS = [
    "https://www.skolverket.se/undervisning/grundskolan/laroplan-och-kursplaner-for-grundskolan",
    "https://www.skolverket.se/undervisning/gymnasieskolan/laroplan-program-och-amnen-i-gymnasieskolan",
    "https://www.skolverket.se/regler-och-ansvar/sok-forordningar-och-foreskrifter-skolfs",
    "https://www.skolverket.se/styrning-och-ansvar/regler-och-ansvar/allmanna-rad",
    "https://www.skolverket.se/sok-publikationer",
    "https://www.skolverket.se/publikationsserier/styrdokument",
    "https://www.skolverket.se/publikationsserier/allmanna-rad",
]

# Additional direct SKOLFS API endpoints
SKOLFS_BASE = "https://skolfs.skolverket.se/api/document"


class DeepSkolverketScraper:
    """Deep recursive scraper for Skolverket"""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except:
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )

        self.session: Optional[aiohttp.ClientSession] = None
        self.visited_urls: set[str] = set()
        self.documents: list[dict] = []
        self.stats = {
            "urls_crawled": 0,
            "pdfs_found": 0,
            "pages_found": 0,
            "new_added": 0,
            "duplicates": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkolverketDeepScraper/1.0)"},
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

    def _normalize_url(self, url: str) -> str:
        """Remove fragments and normalize URL"""
        parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, "")
        )

    def _is_skolverket_url(self, url: str) -> bool:
        """Check if URL belongs to skolverket.se domain"""
        return "skolverket.se" in url or "skolfs.skolverket.se" in url

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page with error handling"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    # Check if it's HTML or PDF
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" in content_type:
                        return await response.text()
                    elif "application/pdf" in content_type:
                        # It's a PDF - add it as document
                        await self.add_pdf_document(url)
                        return None
                else:
                    logger.debug(f"HTTP {response.status} for {url}")
                    return None
        except asyncio.TimeoutError:
            logger.warning(f"Timeout: {url}")
            self.stats["errors"] += 1
            return None
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def add_pdf_document(self, url: str, title: str = None):
        """Add PDF document to collection"""
        if not title:
            title = Path(urlparse(url).path).name

        doc_id = self._generate_doc_id(url, title)

        if not self._exists_in_db(doc_id):
            # Determine category from URL
            category = "unknown"
            if "laroplan" in url.lower():
                category = "laroplan"
            elif "SKOLFS" in url or "skolfs" in url:
                category = "foreskrift"
            elif "allmanna-rad" in url.lower():
                category = "allmanna_rad"
            elif "statistik" in url.lower():
                category = "statistik"

            doc = {
                "id": doc_id,
                "url": url,
                "title": title,
                "category": category,
                "type": "pdf",
                "content": f"PDF Document: {title}\nURL: {url}",
            }

            self.documents.append(doc)
            self.stats["pdfs_found"] += 1
            logger.info(f"📄 PDF: {title}")

    async def add_page_document(self, url: str, title: str, content: str):
        """Add webpage document"""
        doc_id = self._generate_doc_id(url, title)

        if not self._exists_in_db(doc_id) and len(content) > 200:
            category = "unknown"
            if "laroplan" in url.lower():
                category = "laroplan"
            elif "SKOLFS" in url or "skolfs" in url:
                category = "foreskrift"
            elif "allmanna-rad" in url.lower():
                category = "allmanna_rad"

            doc = {
                "id": doc_id,
                "url": url,
                "title": title,
                "category": category,
                "type": "webpage",
                "content": content,
            }

            self.documents.append(doc)
            self.stats["pages_found"] += 1

    async def extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract all relevant links from HTML"""
        soup = BeautifulSoup(html, "lxml")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)
            normalized = self._normalize_url(full_url)

            # Only follow skolverket.se links
            if self._is_skolverket_url(normalized):
                links.append(normalized)

        return list(set(links))  # Deduplicate

    async def crawl_page(self, url: str, depth: int = 0, max_depth: int = 3):
        """Recursively crawl a page"""
        if depth > max_depth:
            return

        normalized_url = self._normalize_url(url)

        # Skip if already visited
        if normalized_url in self.visited_urls:
            return

        self.visited_urls.add(normalized_url)
        self.stats["urls_crawled"] += 1

        logger.info(f"[Depth {depth}] Crawling: {url}")

        html = await self.fetch_page(url)
        if not html:
            return

        # Extract and store page content
        soup = BeautifulSoup(html, "lxml")

        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Get page title
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        # Get main content
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile("content|main", re.I))
            or soup.find("body")
        )

        if main:
            content = main.get_text(separator="\n", strip=True)
            content = re.sub(r"\n{3,}", "\n\n", content)

            # Store page if substantial
            await self.add_page_document(url, page_title, content)

        # Find all links
        links = await self.extract_links(html, url)

        # Identify PDFs immediately
        pdf_links = [link for link in links if link.endswith(".pdf")]
        for pdf_url in pdf_links:
            await self.add_pdf_document(pdf_url)

        # Recursively crawl other links (but limit to avoid infinite crawl)
        page_links = [link for link in links if not link.endswith(".pdf")]

        # Only crawl deeper if we're not too deep and URL looks relevant
        if depth < max_depth:
            relevant_links = [
                link
                for link in page_links
                if any(
                    kw in link.lower()
                    for kw in [
                        "laroplan",
                        "skolfs",
                        "foreskrift",
                        "allmanna-rad",
                        "statistik",
                        "publikation",
                        "styrdokument",
                    ]
                )
            ]

            # Limit to avoid explosion
            for link in relevant_links[:20]:  # Max 20 links per page
                await self.crawl_page(link, depth + 1, max_depth)
                await asyncio.sleep(0.5)  # Rate limiting

    async def scrape_skolfs_api(self):
        """Direct API scraping for SKOLFS documents"""
        logger.info("Scraping SKOLFS API endpoints...")

        current_year = datetime.now().year

        for year in range(2020, current_year + 1):
            logger.info(f"Checking SKOLFS {year}...")

            for num in range(1, 600):  # Up to 600 per year
                for doc_type in ["GRUNDFORFATTNING", "ANDRINGSFORFATTNING"]:
                    skolfs_id = f"{year}:{num}"
                    api_url = f"{SKOLFS_BASE}/{doc_type}/{skolfs_id}/pdf"

                    # Try to fetch (head request to check if exists)
                    try:
                        async with self.session.head(api_url) as response:
                            if response.status == 200:
                                title = f"SKOLFS {skolfs_id} ({doc_type})"
                                await self.add_pdf_document(api_url, title)
                    except:
                        pass  # Doesn't exist

                # Rate limiting
                if num % 50 == 0:
                    await asyncio.sleep(1)

    def store_all_documents(self):
        """Batch store all collected documents"""
        if not self.documents:
            logger.warning("No documents to store")
            return

        batch_size = 1000
        for i in range(0, len(self.documents), batch_size):
            batch = self.documents[i : i + batch_size]

            ids = [doc["id"] for doc in batch]
            texts = [doc["content"] for doc in batch]
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
                logger.info(f"Stored batch of {len(batch)} documents")
            except Exception as e:
                logger.error(f"Error storing batch: {e}")
                self.stats["errors"] += 1

    async def run(self):
        """Main workflow"""
        logger.info("=" * 60)
        logger.info("SKOLVERKET DEEP SCRAPER STARTING")
        logger.info("=" * 60)

        start_time = time.time()

        # Crawl seed URLs
        for seed_url in SEED_URLS:
            logger.info(f"\n=== Crawling seed: {seed_url} ===")
            await self.crawl_page(seed_url, depth=0, max_depth=2)
            await asyncio.sleep(2)

        # Scrape SKOLFS API (disabled by default - too slow)
        # await self.scrape_skolfs_api()

        # Store all documents
        logger.info("\n=== Storing documents ===")
        self.store_all_documents()

        elapsed = time.time() - start_time

        # Report
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"URLs crawled: {self.stats['urls_crawled']}")
        logger.info(f"PDFs found: {self.stats['pdfs_found']}")
        logger.info(f"Pages found: {self.stats['pages_found']}")
        logger.info(f"Total documents: {len(self.documents)}")
        logger.info(f"New documents added: {self.stats['new_added']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Time elapsed: {elapsed:.2f}s")

        if self.stats["new_added"] < MIN_DOC_THRESHOLD:
            logger.warning(
                f"\n⚠️  WARNING: Only {self.stats['new_added']} documents (threshold: {MIN_DOC_THRESHOLD})"
            )
        else:
            logger.info(f"\n✓ Success: {self.stats['new_added']} documents collected")

        return self.stats


async def main():
    async with DeepSkolverketScraper() as scraper:
        stats = await scraper.run()

        # Write report
        report_path = Path(__file__).parent / "skolverket_deep_report.json"
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": SOURCE_NAME,
            "method": "deep_recursive_crawl",
            "stats": stats,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "threshold_met": stats["new_added"] >= MIN_DOC_THRESHOLD,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n📄 Report: {report_path}")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
