#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - LÄKEMEDELSVERKET

Scrapes documents from lakemedelsverket.se:
- Föreskrifter (LVFS/HSLF-FS)
- Rapporter
- Vägledningar
- Produktinformation

Stores in ChromaDB collection 'swedish_gov_docs' with metadata source: "lakemedelsverket"
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

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
BASE_URL = "https://www.lakemedelsverket.se"
MIN_DOCS_THRESHOLD = 100

# Document categories to scrape
CATEGORIES = [
    {
        "name": "Föreskrifter",
        "url": "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter",
        "type": "listing",
    },
    {
        "name": "Vägledningar",
        "url": "https://www.lakemedelsverket.se/sv/lagar-och-regler/vagledningar",
        "type": "listing",
    },
]

# Years to scrape for föreskrifter (HSLF-FS format started around 2021)
YEARS = list(range(2015, 2026))  # 2015-2025


class LakemedelsverketScraper:
    """Scraper for Läkemedelsverket documents"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Swedish government documents from multiple sources"},
        )
        self.scraped_urls: set[str] = set()
        self.documents: list[dict] = []

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
        """Generate unique document ID from URL and title"""
        content = f"{url}|{title}".encode()
        return hashlib.sha256(content).hexdigest()[:16]

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content with error handling"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Status {response.status} for {url}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content from page"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Try to find main content area
        main_content = (
            soup.find("main") or soup.find("article") or soup.find("div", class_="content")
        )

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract metadata from page"""
        metadata = {
            "source": "lakemedelsverket",
            "url": url,
            "scraped_at": datetime.now().isoformat(),
        }

        # Try to extract date
        date_patterns = [r"(\d{4}-\d{2}-\d{2})", r"(\d{2}/\d{2}/\d{4})", r"(\d{1,2}\s+\w+\s+\d{4})"]

        page_text = soup.get_text()
        for pattern in date_patterns:
            match = re.search(pattern, page_text)
            if match:
                metadata["date"] = match.group(1)
                break

        # Try to extract document type from URL or content
        url_lower = url.lower()
        if "lvfs" in url_lower or "LVFS" in page_text[:500]:
            metadata["document_type"] = "Föreskrift LVFS"
        elif "hslf-fs" in url_lower or "HSLF-FS" in page_text[:500]:
            metadata["document_type"] = "Föreskrift HSLF-FS"
        elif "rapport" in url_lower:
            metadata["document_type"] = "Rapport"
        elif "vagledning" in url_lower:
            metadata["document_type"] = "Vägledning"
        else:
            metadata["document_type"] = "Dokument"

        return metadata

    async def scrape_document_page(self, url: str, category: str) -> Optional[dict]:
        """Scrape a single document page"""
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)

        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title_tag = soup.find("h1") or soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"

        # Extract content
        content = self.extract_text_content(soup)

        if len(content) < 100:  # Skip pages with minimal content
            logger.debug(f"Skipping {url} - insufficient content")
            return None

        # Extract metadata
        metadata = self.extract_metadata(soup, url)
        metadata["category"] = category

        doc = {
            "id": self.generate_doc_id(url, title),
            "title": title,
            "content": content,
            "metadata": metadata,
        }

        logger.info(f"Scraped: {title[:60]}... ({len(content)} chars)")
        return doc

    async def scrape_search_results(
        self, url: str, category: str, max_pages: int = 20
    ) -> list[str]:
        """Scrape search results and return document URLs"""
        doc_urls = []

        for page in range(1, max_pages + 1):
            page_url = url.replace("page=1", f"page={page}")

            html = await self.fetch_page(page_url)
            if not html:
                break

            soup = BeautifulSoup(html, "html.parser")

            # Find all links that look like documents
            links = soup.find_all("a", href=True)
            found_on_page = 0

            for link in links:
                href = link["href"]
                full_url = urljoin(BASE_URL, href)

                # Only follow internal links
                if not full_url.startswith(BASE_URL):
                    continue

                # Skip search, menu, and navigation links
                skip_patterns = ["/sok", "/meny", "/javascript:", "#", "mailto:", ".jpg", ".png"]
                if any(pattern in full_url for pattern in skip_patterns):
                    continue

                if full_url not in doc_urls and full_url not in self.scraped_urls:
                    doc_urls.append(full_url)
                    found_on_page += 1

            logger.info(f"Page {page}: found {found_on_page} new URLs")

            if found_on_page == 0:  # No new results
                break

            await asyncio.sleep(1)  # Rate limiting

        return doc_urls

    async def scrape_listing_page(self, url: str, category: str) -> list[str]:
        """Scrape a listing/index page for document links"""
        doc_urls = []

        html = await self.fetch_page(url)
        if not html:
            return doc_urls

        soup = BeautifulSoup(html, "html.parser")

        # Find all links
        links = soup.find_all("a", href=True)

        for link in links:
            href = link["href"]
            full_url = urljoin(BASE_URL, href)

            # Only follow internal links
            if not full_url.startswith(BASE_URL):
                continue

            # Skip unwanted links
            skip_patterns = ["/sok", "/meny", "javascript:", "#", "mailto:", ".jpg", ".png"]
            if any(pattern in full_url for pattern in skip_patterns):
                continue

            # For föreskrifter: match pattern like /sv/lagar-och-regler/foreskrifter/2024-26
            if category == "Föreskrifter":
                if re.search(r"/foreskrifter/\d{4}-\d+", full_url):
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)
            # For vägledningar: match pattern like /sv/lagar-och-regler/vagledningar/...
            elif category == "Vägledningar":
                if "/vagledningar/" in full_url and full_url != url:
                    if full_url not in doc_urls:
                        doc_urls.append(full_url)

        logger.info(f"Found {len(doc_urls)} document URLs from listing")
        return doc_urls

    async def scrape_year_index(self, year: int) -> list[str]:
        """Scrape föreskrifter for a specific year"""
        doc_urls = []

        # Try common patterns for year-specific pages
        patterns = [
            f"{BASE_URL}/sv/lagar-och-regler/foreskrifter?year={year}",
            f"{BASE_URL}/sv/lagar-och-regler/foreskrifter/{year}",
        ]

        for pattern_url in patterns:
            html = await self.fetch_page(pattern_url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                links = soup.find_all("a", href=True)

                for link in links:
                    href = link["href"]
                    full_url = urljoin(BASE_URL, href)

                    # Match föreskrift pattern for this year
                    if re.search(rf"/foreskrifter/{year}-\d+", full_url):
                        if full_url not in doc_urls:
                            doc_urls.append(full_url)

                if doc_urls:
                    break  # Found results with this pattern

        return doc_urls

    async def scrape_category(self, category: dict):
        """Scrape all documents from a category"""
        logger.info(f"\n=== Scraping category: {category['name']} ===")

        doc_urls = await self.scrape_listing_page(category["url"], category["name"])

        # For föreskrifter, also try year-by-year scraping
        if category["name"] == "Föreskrifter" and len(doc_urls) < 50:
            logger.info("Attempting year-by-year scraping for föreskrifter...")
            for year in YEARS:
                year_urls = await self.scrape_year_index(year)
                for url in year_urls:
                    if url not in doc_urls:
                        doc_urls.append(url)
                logger.info(f"Year {year}: found {len(year_urls)} URLs")
                await asyncio.sleep(1)

        logger.info(f"Found {len(doc_urls)} total URLs to scrape")

        # Scrape documents with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

        async def scrape_with_semaphore(url):
            async with semaphore:
                return await self.scrape_document_page(url, category["name"])

        tasks = [scrape_with_semaphore(url) for url in doc_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None and exceptions
        docs = [r for r in results if isinstance(r, dict)]
        self.documents.extend(docs)

        logger.info(f"Category {category['name']}: scraped {len(docs)} documents")

    async def scrape_all(self):
        """Scrape all categories"""
        for category in CATEGORIES:
            await self.scrape_category(category)
            await asyncio.sleep(2)  # Delay between categories

    def store_documents(self):
        """Store documents in ChromaDB"""
        if not self.documents:
            logger.warning("No documents to store")
            return

        logger.info(f"\nStoring {len(self.documents)} documents in ChromaDB...")

        ids = [doc["id"] for doc in self.documents]
        documents = [doc["content"] for doc in self.documents]
        metadatas = [doc["metadata"] for doc in self.documents]

        # Add documents in batches
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            batch_ids = ids[i : i + batch_size]
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]

            try:
                self.collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
                logger.info(f"Stored batch {i//batch_size + 1} ({len(batch_ids)} docs)")
            except Exception as e:
                logger.error(f"Error storing batch: {e}")

        logger.info("✓ All documents stored")

    def generate_report(self) -> dict:
        """Generate scraping report"""
        # Count by document type
        type_counts = {}
        for doc in self.documents:
            doc_type = doc["metadata"].get("document_type", "Unknown")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        # Check if we met the threshold
        warning = len(self.documents) < MIN_DOCS_THRESHOLD

        report = {
            "source": "lakemedelsverket",
            "timestamp": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "unique_urls": len(self.scraped_urls),
            "document_types": type_counts,
            "warning": warning,
            "warning_message": f"Only {len(self.documents)} documents found (threshold: {MIN_DOCS_THRESHOLD})"
            if warning
            else None,
            "chromadb_collection": COLLECTION_NAME,
            "chromadb_path": CHROMADB_PATH,
            "sample_documents": [
                {
                    "title": doc["title"],
                    "url": doc["metadata"]["url"],
                    "type": doc["metadata"].get("document_type"),
                    "content_length": len(doc["content"]),
                }
                for doc in self.documents[:5]
            ],
        }

        return report


async def main():
    """Main execution"""
    logger.info("=== OPERATION MYNDIGHETS-SWEEP - LÄKEMEDELSVERKET ===\n")

    async with LakemedelsverketScraper() as scraper:
        # Scrape all documents
        await scraper.scrape_all()

        # Store in ChromaDB
        scraper.store_documents()

        # Generate report
        report = scraper.generate_report()

        # Save report
        report_path = Path(__file__).parent / "lakemedelsverket_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Print summary
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE - LÄKEMEDELSVERKET")
        print("=" * 60)
        print(f"Total documents: {report['total_documents']}")
        print(f"Unique URLs: {report['unique_urls']}")
        print("\nDocument types:")
        for doc_type, count in report["document_types"].items():
            print(f"  {doc_type}: {count}")

        if report["warning"]:
            print(f"\n⚠️  WARNING: {report['warning_message']}")
        else:
            print(f"\n✓ Threshold met ({MIN_DOCS_THRESHOLD}+ documents)")

        print(f"\nReport saved to: {report_path}")
        print("=" * 60)

        return report


if __name__ == "__main__":
    asyncio.run(main())
