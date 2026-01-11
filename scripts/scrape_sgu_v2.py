#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - SGU (Sveriges geologiska undersökning) V2

Strategy:
1. Query GeoLagret API for all publication series
2. Scrape individual report pages
3. Download and extract PDF content where available
4. Scrape föreskrifter (SGU-FS) pages
5. Store in ChromaDB with source="sgu"
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
GEOLAGRET_API = "https://apps.sgu.se/geolagret"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 15

# GeoLagret metadata API patterns
GEOLAGRET_METADATA_PATTERN = re.compile(r"GetMetaDataById\?id=(md-[a-f0-9-]+)")

# Known publication series and föreskrifter
SEED_URLS = [
    # Nypublicerat pages (chronological listings)
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2024/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2023/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2022/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2021/",
    "https://www.sgu.se/produkter-och-tjanster/rapporter/nypublicerat/publicerat-2020/",
    # Föreskrifter
    "https://www.sgu.se/om-sgu/verksamhet/foreskrifter/",
    # Periodiska publikationer
    "https://www.sgu.se/mineralnaring/mineralstatistik/mineralmarknaden-rapportserie/",
    "https://www.sgu.se/mineralnaring/mineralstatistik/bergverksstatistik/",
]


class SGUScraperV2:
    """Advanced scraper for SGU using GeoLagret API + web scraping"""

    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Swedish government documents from multiple sources"},
        )
        self.scraped_urls: set[str] = set()
        self.scraped_metadata_ids: set[str] = set()
        self.documents: list[dict] = []
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=45)
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

    async def fetch_geolagret_metadata(self, metadata_id: str) -> dict | None:
        """Fetch metadata from GeoLagret API"""
        if metadata_id in self.scraped_metadata_ids:
            return None

        self.scraped_metadata_ids.add(metadata_id)
        url = f"{GEOLAGRET_API}/GetMetaDataById?id={metadata_id}"

        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = None
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        if not title:
            return None

        # Extract description/abstract
        content_parts = []

        # Look for abstract/description
        for div in soup.find_all("div", class_=re.compile(r"abstract|description|content")):
            text = div.get_text(strip=True)
            if text and len(text) > 50:
                content_parts.append(text)

        # Extract all paragraphs
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text and len(text) > 30:
                content_parts.append(text)

        content = "\n\n".join(content_parts)

        if len(content) < 100:
            return None

        # Extract year from title or metadata
        year = "unknown"
        year_match = re.search(r"(\d{4})", title)
        if year_match:
            year = year_match.group(1)

        # Determine doc type
        doc_type = "rapport"
        title_lower = title.lower()
        if "prospektering" in title_lower:
            doc_type = "prospekteringsrapport"
        elif "sgu-rapport" in title_lower or "sgu-fs" in title_lower:
            doc_type = "rapport"
        elif "periodisk" in title_lower:
            doc_type = "periodisk_publikation"

        return {
            "title": title,
            "content": content,
            "url": url,
            "doc_type": doc_type,
            "publication_date": year,
            "source": "sgu",
            "source_type": "geolagret",
            "scraped_at": datetime.now().isoformat(),
        }

    async def scrape_foreskrift_page(self, url: str) -> dict | None:
        """Scrape a föreskrift page"""
        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = None
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        if not title:
            return None

        # Extract content
        content_parts = []
        main = soup.find("main") or soup.find("article")

        if main:
            for elem in main.find_all(["p", "h2", "h3", "li"]):
                text = elem.get_text(strip=True)
                if text and len(text) > 10:
                    content_parts.append(text)

        content = "\n".join(content_parts)

        if len(content) < 100:
            return None

        # Extract SGU-FS number
        fs_number = "unknown"
        fs_match = re.search(r"SGU-FS\s+(\d{4}:\d+)", title + " " + content)
        if fs_match:
            fs_number = fs_match.group(1)

        # Extract year
        year = "unknown"
        year_match = re.search(r"(\d{4})", title)
        if year_match:
            year = year_match.group(1)

        return {
            "title": title,
            "content": content,
            "url": url,
            "doc_type": "föreskrift",
            "fs_number": fs_number,
            "publication_date": year,
            "source": "sgu",
            "source_type": "foreskrift",
            "scraped_at": datetime.now().isoformat(),
        }

    async def scrape_publication_page(self, url: str) -> dict | None:
        """Scrape a regular publication page"""
        if url in self.scraped_urls:
            return None

        self.scraped_urls.add(url)

        html = await self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = None
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        if not title:
            return None

        # Extract content
        content_parts = []
        main = soup.find("main") or soup.find("article")

        if main:
            for elem in main.find_all(["p", "h2", "h3"]):
                text = elem.get_text(strip=True)
                if text and len(text) > 20:
                    content_parts.append(text)

        content = "\n\n".join(content_parts)

        if len(content) < 100:
            return None

        # Extract year
        year = "unknown"
        year_match = re.search(r"(\d{4})", title)
        if year_match:
            year = year_match.group(1)

        # Determine type
        doc_type = "publikation"
        if "rapport" in title.lower():
            doc_type = "rapport"
        elif "mineral" in title.lower():
            doc_type = "mineralrapport"

        return {
            "title": title,
            "content": content,
            "url": url,
            "doc_type": doc_type,
            "publication_date": year,
            "source": "sgu",
            "source_type": "webpage",
            "scraped_at": datetime.now().isoformat(),
        }

    async def discover_geolagret_links(self, seed_url: str) -> list[str]:
        """Discover GeoLagret metadata links from a page"""
        html = await self.fetch_page(seed_url)
        if not html:
            return []

        # Find all GeoLagret metadata IDs
        metadata_ids = GEOLAGRET_METADATA_PATTERN.findall(html)
        return [f"{GEOLAGRET_API}/GetMetaDataById?id={mid}" for mid in set(metadata_ids)]

    async def discover_publication_links(self, seed_url: str) -> list[str]:
        """Discover publication links from a listing page"""
        html = await self.fetch_page(seed_url)
        if not html:
            return []

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
            if "sgu.se" not in href:
                continue

            # Clean URL
            href = href.split("#")[0].split("?")[0]

            # Filter relevant URLs
            href_lower = href.lower()
            if any(
                keyword in href_lower
                for keyword in [
                    "rapport",
                    "publikation",
                    "foreskrift",
                    "mineral",
                    "sgu-fs",
                    "bergverksstatistik",
                ]
            ):
                links.add(href)

        return list(links)

    async def run(self):
        """Main scraping logic"""
        logger.info("=" * 60)
        logger.info("OPERATION MYNDIGHETS-SWEEP - SGU V2")
        logger.info("=" * 60)

        # Phase 1: Discover all URLs
        logger.info("\nPhase 1: Discovering URLs...")

        geolagret_links = set()
        publication_links = set()
        foreskrift_links = set()

        for seed_url in SEED_URLS:
            logger.info(f"Crawling: {seed_url}")

            # Discover GeoLagret links
            geo_links = await self.discover_geolagret_links(seed_url)
            geolagret_links.update(geo_links)

            # Discover publication links
            pub_links = await self.discover_publication_links(seed_url)

            for link in pub_links:
                if "foreskrift" in link.lower():
                    foreskrift_links.add(link)
                else:
                    publication_links.add(link)

            await asyncio.sleep(0.3)

        logger.info(f"Discovered {len(geolagret_links)} GeoLagret documents")
        logger.info(f"Discovered {len(publication_links)} publications")
        logger.info(f"Discovered {len(foreskrift_links)} föreskrifter")

        # Phase 2: Scrape GeoLagret metadata
        logger.info("\nPhase 2: Scraping GeoLagret metadata...")

        tasks = []
        for url in geolagret_links:
            metadata_id = url.split("id=")[-1]
            tasks.append(self.fetch_geolagret_metadata(metadata_id))

            if len(tasks) >= 50:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                        logger.info(f"✓ GeoLagret: {result['title'][:60]}...")
                tasks = []
                logger.info(f"Progress: {len(self.documents)} documents")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Phase 3: Scrape föreskrifter
        logger.info("\nPhase 3: Scraping föreskrifter...")

        tasks = []
        for url in foreskrift_links:
            tasks.append(self.scrape_foreskrift_page(url))

            if len(tasks) >= 20:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                        logger.info(f"✓ Föreskrift: {result['title'][:60]}...")
                tasks = []

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Phase 4: Scrape publications
        logger.info("\nPhase 4: Scraping publications...")

        tasks = []
        for url in list(publication_links)[:100]:  # Limit to avoid overload
            tasks.append(self.scrape_publication_page(url))

            if len(tasks) >= 20:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, dict):
                        self.documents.append(result)
                        logger.info(f"✓ Publication: {result['title'][:60]}...")
                tasks = []

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, dict):
                    self.documents.append(result)

        # Phase 5: Store in ChromaDB
        logger.info(f"\nPhase 5: Storing {len(self.documents)} documents...")

        if self.documents:
            ids = []
            documents = []
            metadatas = []

            for doc in self.documents:
                doc_id = self.generate_doc_id(doc["url"], doc["title"])
                ids.append(doc_id)
                documents.append(doc["content"])

                metadata = {
                    "title": doc["title"],
                    "url": doc["url"],
                    "source": "sgu",
                    "doc_type": doc["doc_type"],
                    "publication_date": doc["publication_date"],
                    "scraped_at": doc["scraped_at"],
                }

                # Add optional fields
                if "fs_number" in doc:
                    metadata["fs_number"] = doc["fs_number"]
                if "source_type" in doc:
                    metadata["source_type"] = doc["source_type"]

                metadatas.append(metadata)

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
        source_type_counts = {}

        for doc in self.documents:
            doc_type = doc["doc_type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

            if "source_type" in doc:
                source_type = doc["source_type"]
                source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1

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
            "source_types": source_type_counts,
            "geolagret_metadata_scraped": len(self.scraped_metadata_ids),
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
    async with SGUScraperV2() as scraper:
        report = await scraper.run()

        # Print report
        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))

        # Save report
        report_path = Path(__file__).parent / "sgu_report_v2.json"
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
