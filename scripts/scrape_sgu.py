#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - SGU (Sveriges geologiska undersökning)

Scraping strategy:
1. Search for publikationer, rapporter, kartor, föreskrifter on sgu.se
2. Parse publication listings and documents
3. Extract metadata and content
4. Store in ChromaDB with source="sgu"
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path

import aiohttp
import chromadb
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
BASE_URL = "https://www.sgu.se"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 10

# Known SGU sections
SEED_URLS = [
    "https://www.sgu.se/om-sgu/publikationer/",
    "https://www.sgu.se/samhallsplanering/",
    "https://www.sgu/om-sgu/nyheter/",
    "https://www.sgu.se/grundvatten/",
    "https://www.sgu.se/mineral/",
    "https://www.sgu.se/om-sgu/lagar-och-foreskrifter/",
]

# SGU publication series patterns
PUBLICATION_PATTERNS = [
    r"/publikationer/sgु-rapporter?/(\d+)",
    r"/publikationer/sgu-rapport-([^/]+)",
    r"/publikationer/periodiska-publikationer",
    r"/publikationer/rapporter",
    r"/publikationer/oversikter",
    r"/produkter/kartor",
]


class SGUScraper:
    """Scraper for Sveriges geologiska undersökning (SGU)"""

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

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
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
                    elif response.status == 404:
                        return None
                    else:
                        logger.debug(f"Status {response.status} for {url}")
                        return None
            except asyncio.TimeoutError:
                logger.debug(f"Timeout: {url}")
                return None
            except Exception as e:
                logger.debug(f"Error fetching {url}: {e}")
                return None

    def extract_links(self, html: str, base_url: str) -> set[str]:
        """Extract all internal links from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        links = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]

            # Convert relative to absolute
            if href.startswith("/"):
                href = f"{BASE_URL}{href}"
            elif not href.startswith("http"):
                continue

            # Only SGU links
            if "sgu.se" in href:
                # Clean URL
                href = href.split("#")[0].split("?")[0]
                links.add(href)

        return links

    def extract_document_metadata(self, soup: BeautifulSoup, url: str) -> dict | None:
        """Extract document metadata from page"""

        # Try to find title
        title = None
        if soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)
        elif soup.find("title"):
            title = soup.find("title").get_text(strip=True)

        if not title:
            return None

        # Extract main content
        content_parts = []

        # Look for main content areas
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|main|article"))
        )

        if main_content:
            # Extract paragraphs
            for p in main_content.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 20:
                    content_parts.append(text)

            # Extract headings with context
            for heading in main_content.find_all(["h2", "h3", "h4"]):
                content_parts.append(f"\n{heading.get_text(strip=True)}\n")

        content = "\n".join(content_parts)

        # Must have substantial content
        if len(content) < 100:
            return None

        # Extract publication date if available
        pub_date = None
        date_patterns = [
            soup.find("time"),
            soup.find("meta", attrs={"property": "article:published_time"}),
            soup.find("span", class_=re.compile(r"date|published")),
        ]

        for pattern in date_patterns:
            if pattern:
                if pattern.name == "time" and pattern.get("datetime"):
                    pub_date = pattern["datetime"]
                    break
                elif pattern.name == "meta" and pattern.get("content"):
                    pub_date = pattern["content"]
                    break
                else:
                    date_text = pattern.get_text(strip=True)
                    # Try to extract YYYY-MM-DD
                    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                    if date_match:
                        pub_date = date_match.group(1)
                        break

        # Determine document type
        doc_type = "unknown"
        url_lower = url.lower()

        if "rapport" in url_lower or "rapport" in title.lower():
            doc_type = "rapport"
        elif "karta" in url_lower or "karta" in title.lower():
            doc_type = "karta"
        elif "foreskrift" in url_lower or "föreskrift" in title.lower():
            doc_type = "föreskrift"
        elif "oversikt" in url_lower or "översikt" in title.lower():
            doc_type = "översikt"
        elif "publikation" in url_lower:
            doc_type = "publikation"
        elif "nyhet" in url_lower:
            doc_type = "nyhet"

        return {
            "title": title,
            "content": content,
            "url": url,
            "doc_type": doc_type,
            "publication_date": pub_date or "unknown",
            "source": "sgu",
            "scraped_at": datetime.now().isoformat(),
        }

    async def scrape_url(self, url: str) -> dict | None:
        """Scrape a single URL"""
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)

        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        metadata = self.extract_document_metadata(soup, url)

        if metadata:
            logger.info(f"✓ Scraped: {metadata['title'][:60]}... ({metadata['doc_type']})")
            return metadata

        return None

    async def crawl_recursive(
        self, start_url: str, max_depth: int = 3, current_depth: int = 0
    ) -> list[str]:
        """Recursively crawl and discover URLs"""
        if current_depth >= max_depth:
            return []

        html = await self.fetch_page(start_url)
        if not html:
            return []

        discovered = self.extract_links(html, start_url)

        # Filter for relevant URLs
        relevant = set()
        for url in discovered:
            url_lower = url.lower()
            if any(
                keyword in url_lower
                for keyword in [
                    "publikation",
                    "rapport",
                    "karta",
                    "foreskrift",
                    "oversikt",
                    "nyhet",
                    "press",
                    "dokument",
                ]
            ):
                relevant.add(url)

        return list(relevant)

    async def run(self):
        """Main scraping logic"""
        logger.info("=" * 60)
        logger.info("OPERATION MYNDIGHETS-SWEEP - SGU")
        logger.info("=" * 60)

        # Phase 1: Discover URLs
        logger.info("\nPhase 1: Discovering URLs...")
        all_urls = set(SEED_URLS)

        for seed_url in SEED_URLS:
            logger.info(f"Crawling: {seed_url}")
            discovered = await self.crawl_recursive(seed_url, max_depth=2)
            all_urls.update(discovered)
            await asyncio.sleep(0.5)  # Rate limiting

        logger.info(f"Discovered {len(all_urls)} URLs")

        # Phase 2: Scrape documents
        logger.info("\nPhase 2: Scraping documents...")

        tasks = []
        for url in all_urls:
            tasks.append(self.scrape_url(url))

            # Process in batches
            if len(tasks) >= 50:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                tasks = []
                logger.info(f"Progress: {len(self.documents)} documents scraped")

        # Process remaining
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Phase 3: Store in ChromaDB
        logger.info(f"\nPhase 3: Storing {len(self.documents)} documents...")

        if self.documents:
            ids = []
            documents = []
            metadatas = []

            for doc in self.documents:
                doc_id = self.generate_doc_id(doc["url"], doc["title"])
                ids.append(doc_id)
                documents.append(doc["content"])
                metadatas.append(
                    {
                        "title": doc["title"],
                        "url": doc["url"],
                        "source": "sgu",
                        "doc_type": doc["doc_type"],
                        "publication_date": doc["publication_date"],
                        "scraped_at": doc["scraped_at"],
                    }
                )

            # Batch insert
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i : i + batch_size]
                batch_docs = documents[i : i + batch_size]
                batch_meta = metadatas[i : i + batch_size]

                try:
                    self.collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
                    logger.info(
                        f"Stored batch {i // batch_size + 1}/{(len(ids) - 1) // batch_size + 1}"
                    )
                except Exception as e:
                    logger.error(f"Error storing batch: {e}")

        # Generate report
        report = self.generate_report()
        return report

    def generate_report(self) -> dict:
        """Generate final report"""
        total_docs = len(self.documents)

        # Count by type
        type_counts = {}
        for doc in self.documents:
            doc_type = doc["doc_type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

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
            "urls_crawled": len(self.scraped_urls),
            "status": status,
            "threshold": MIN_DOCS_THRESHOLD,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "timestamp": datetime.now().isoformat(),
        }

        return report


async def main():
    """Entry point"""
    async with SGUScraper() as scraper:
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


if __name__ == "__main__":
    asyncio.run(main())
