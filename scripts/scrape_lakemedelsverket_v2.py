#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - LÄKEMEDELSVERKET V2

Direct scraping strategy:
1. Use WebSearch to discover all föreskrifter URLs
2. Extract embedded JSON data from each page
3. Store in ChromaDB
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import chromadb

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
BASE_URL = "https://www.lakemedelsverket.se"
MIN_DOCS_THRESHOLD = 100

# Known URLs from WebSearch - starting seed
SEED_URLS = [
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-26",
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-28",
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-17",
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-25",
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-12",
    "https://www.lakemedelsverket.se/sv/lagar-och-regler/foreskrifter/2024-14",
]

# Generate URLs for years 2015-2025, numbers 1-99
GENERATED_URLS = []
for year in range(2015, 2026):
    for num in range(1, 100):
        GENERATED_URLS.append(f"{BASE_URL}/sv/lagar-och-regler/foreskrifter/{year}-{num}")


class LakemedelsverketScraperV2:
    """Scraper using embedded JSON extraction"""

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
        """Generate unique document ID"""
        content = f"{url}|{title}".encode()
        return hashlib.sha256(content).hexdigest()[:16]

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 404:
                    return None  # Page doesn't exist, not an error
                else:
                    logger.warning(f"Status {response.status} for {url}")
                    return None
        except asyncio.TimeoutError:
            logger.debug(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return None

    def extract_json_data(self, html: str) -> Optional[dict]:
        """Extract embedded JSON data from <app-root> tag"""
        # Find the app-root content attribute
        pattern = r'<app-root content="({[^"]*})"'
        match = re.search(pattern, html)

        if not match:
            return None

        try:
            # The JSON is HTML-encoded, need to decode
            json_str = match.group(1)
            # Unescape HTML entities
            json_str = json_str.replace("&quot;", '"')
            json_str = json_str.replace("&amp;", "&")
            json_str = json_str.replace("&#x200D;", "")  # Zero-width joiner
            json_str = json_str.replace("&#xA0;", " ")  # Non-breaking space
            json_str = json_str.replace("&#xE4;", "ä")
            json_str = json_str.replace("&#xF6;", "ö")
            json_str = json_str.replace("&#xC4;", "Ä")
            json_str = json_str.replace("&#xF6;", "ö")

            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error extracting JSON: {e}")
            return None

    def extract_text_from_json(self, data: dict) -> str:
        """Extract readable text from JSON structure"""
        texts = []

        # Get heading
        if "heading" in data and data["heading"].get("value"):
            texts.append(data["heading"]["value"])

        # Get mainBody content
        if "mainBody" in data and data["mainBody"].get("value"):
            for item in data["mainBody"]["value"]:
                if isinstance(item, dict):
                    # HTML content
                    if item.get("html"):
                        # Strip HTML tags
                        html_text = re.sub(r"<[^>]+>", " ", item["html"])
                        html_text = html_text.replace("&amp;", "&")
                        html_text = html_text.replace("&nbsp;", " ")
                        html_text = " ".join(html_text.split())
                        if html_text.strip():
                            texts.append(html_text)

                    # Block content
                    if item.get("content") and isinstance(item["content"], dict):
                        content_data = item["content"]

                        # Heading
                        if "heading" in content_data and content_data["heading"].get("value"):
                            texts.append(content_data["heading"]["value"])

                        # Main body
                        if "mainBody" in content_data and content_data["mainBody"].get("value"):
                            body_html = content_data["mainBody"]["value"]
                            body_text = re.sub(r"<[^>]+>", " ", body_html)
                            body_text = body_text.replace("&amp;", "&")
                            body_text = body_text.replace("&nbsp;", " ")
                            body_text = " ".join(body_text.split())
                            if body_text.strip():
                                texts.append(body_text)

        return "\n\n".join(texts)

    async def scrape_document_page(self, url: str) -> Optional[dict]:
        """Scrape a föreskrift page"""
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)

        html = await self.fetch_page(url)
        if not html:
            return None

        # Extract JSON data
        data = self.extract_json_data(html)
        if not data:
            logger.debug(f"No JSON data for {url}")
            return None

        # Extract title
        title = data.get("heading", {}).get("value") or data.get("name", "Untitled")

        # Extract text content
        content = self.extract_text_from_json(data)

        if len(content) < 50:  # Skip if too little content
            logger.debug(f"Insufficient content for {url}")
            return None

        # Extract metadata
        metadata = {
            "source": "lakemedelsverket",
            "url": url,
            "scraped_at": datetime.now().isoformat(),
            "document_type": "Föreskrift",
        }

        # Extract date info
        info_block = data.get("informationBlock", {})
        if "adoptDate" in info_block and info_block["adoptDate"].get("value"):
            metadata["adopt_date"] = info_block["adoptDate"]["value"]

        if "forceDate" in info_block and info_block["forceDate"].get("value"):
            metadata["force_date"] = info_block["forceDate"]["value"]

        # Extract PDF link if available
        if "printedVersion" in info_block and info_block["printedVersion"].get("value"):
            pdf_items = info_block["printedVersion"]["value"]
            if pdf_items and len(pdf_items) > 0:
                pdf_url = pdf_items[0].get("url")
                if pdf_url:
                    metadata["pdf_url"] = BASE_URL + pdf_url if pdf_url.startswith("/") else pdf_url

        doc = {
            "id": self.generate_doc_id(url, title),
            "title": title,
            "content": content,
            "metadata": metadata,
        }

        logger.info(f"Scraped: {title[:60]}... ({len(content)} chars)")
        return doc

    async def scrape_all(self):
        """Scrape all föreskrifter"""
        logger.info(f"Scraping {len(GENERATED_URLS)} potential föreskrifter URLs...")

        # Scrape with concurrency limit
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

        async def scrape_with_semaphore(url):
            async with semaphore:
                return await self.scrape_document_page(url)

        # Process in batches to show progress
        batch_size = 100
        for i in range(0, len(GENERATED_URLS), batch_size):
            batch = GENERATED_URLS[i : i + batch_size]
            tasks = [scrape_with_semaphore(url) for url in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out None and exceptions
            docs = [r for r in results if isinstance(r, dict)]
            self.documents.extend(docs)

            logger.info(
                f"Batch {i//batch_size + 1}/{(len(GENERATED_URLS) + batch_size - 1)//batch_size}: {len(docs)} documents found"
            )

            # Small delay between batches
            await asyncio.sleep(1)

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
        # Count by year
        year_counts = {}
        for doc in self.documents:
            url = doc["metadata"]["url"]
            match = re.search(r"/(\d{4})-\d+", url)
            if match:
                year = match.group(1)
                year_counts[year] = year_counts.get(year, 0) + 1

        # Check threshold
        warning = len(self.documents) < MIN_DOCS_THRESHOLD

        report = {
            "source": "lakemedelsverket",
            "timestamp": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "urls_checked": len(self.scraped_urls),
            "documents_by_year": dict(sorted(year_counts.items())),
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
                    "content_length": len(doc["content"]),
                    "pdf_url": doc["metadata"].get("pdf_url"),
                }
                for doc in self.documents[:10]
            ],
        }

        return report


async def main():
    """Main execution"""
    logger.info("=== OPERATION MYNDIGHETS-SWEEP - LÄKEMEDELSVERKET V2 ===\n")

    async with LakemedelsverketScraperV2() as scraper:
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
        print(f"URLs checked: {report['urls_checked']}")
        print("\nDocuments by year:")
        for year, count in report["documents_by_year"].items():
            print(f"  {year}: {count}")

        if report["warning"]:
            print(f"\n⚠️  WARNING: {report['warning_message']}")
        else:
            print(f"\n✓ Threshold met ({MIN_DOCS_THRESHOLD}+ documents)")

        print(f"\nReport saved to: {report_path}")
        print("=" * 60)

        return report


if __name__ == "__main__":
    asyncio.run(main())
