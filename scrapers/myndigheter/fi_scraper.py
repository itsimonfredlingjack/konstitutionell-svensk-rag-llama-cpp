#!/usr/bin/env python3
"""
Finansinspektionen Document Scraper
Targets: FFFS regulations, Reports, Supervisory decisions, Guidance
Stores in ChromaDB collection: swedish_gov_docs
"""

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from urllib.parse import urljoin

import aiohttp
import chromadb
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm

# Configuration
BASE_URL = "https://www.fi.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "finansinspektionen"
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/fi_scraper_report.json"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 10
TIMEOUT = 30

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """FI document metadata"""

    id: str
    title: str
    url: str
    content: str
    doc_type: str  # fffs, report, supervisory_decision, guidance
    metadata: dict
    scraped_at: str


class FIScraper:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.documents: list[Document] = []
        self.errors: list[dict] = []
        self.stats = {
            "fffs": 0,
            "reports": 0,
            "supervisory_decisions": 0,
            "guidance": 0,
            "total": 0,
            "errors": 0,
        }

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_page(self, url: str, retries: int = 3) -> str | None:
        """Fetch a page with retry logic"""
        for attempt in range(retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {url} (attempt {attempt + 1}/{retries})")
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")

            if attempt < retries - 1:
                await asyncio.sleep(2**attempt)

        self.errors.append({"url": url, "error": "Failed after retries"})
        self.stats["errors"] += 1
        return None

    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text from HTML"""
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Get text
        text = soup.get_text(separator=" ", strip=True)
        # Clean whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    async def scrape_fffs_regulations(self):
        """Scrape FFFS regulations"""
        logger.info("Scraping FFFS regulations...")

        # Base search URL (all regulations)
        search_url = f"{BASE_URL}/sv/vara-register/fffs/sok-fffs/"

        html = await self.fetch_page(search_url)
        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        # Find all regulation links
        links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/vara-register/fffs/sok-fffs/" in href and href.count("/") >= 6:
                full_url = urljoin(BASE_URL, href)
                if full_url not in links:
                    links.append(full_url)

        logger.info(f"Found {len(links)} FFFS regulation pages")

        # Fetch each regulation
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [self._scrape_fffs_doc(url, semaphore) for url in links]

        await tqdm.gather(*tasks, desc="FFFS regulations")

    async def _scrape_fffs_doc(self, url: str, semaphore: asyncio.Semaphore):
        """Scrape individual FFFS document"""
        async with semaphore:
            html = await self.fetch_page(url)
            if not html:
                return

            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"

            # Extract FFFS number from URL or title
            fffs_match = re.search(r"(\d{4}:\d+)", url)
            fffs_number = fffs_match.group(1) if fffs_match else url.split("/")[-2]

            # Extract metadata
            metadata = {
                "source": SOURCE_NAME,
                "doc_type": "fffs",
                "fffs_number": fffs_number,
                "url": url,
            }

            # Look for status, type, category
            for elem in soup.find_all(["p", "span", "div"]):
                text = elem.get_text(strip=True).lower()
                if "gällande" in text:
                    metadata["status"] = "active"
                elif "upphävd" in text:
                    metadata["status"] = "repealed"
                if "grundförfattning" in text:
                    metadata["regulation_type"] = "base"
                elif "ändringsförfattning" in text:
                    metadata["regulation_type"] = "amendment"

            # Extract content
            content = self.extract_text(soup)

            doc = Document(
                id=f"fi_fffs_{fffs_number}",
                title=title,
                url=url,
                content=content,
                doc_type="fffs",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["fffs"] += 1
            self.stats["total"] += 1

    async def scrape_reports(self):
        """Scrape reports from various categories"""
        logger.info("Scraping reports...")

        report_categories = [
            "/sv/publicerat/rapporter/stabilitetsrapport/",
            "/sv/publicerat/rapporter/konsumentskyddsrapport/",
            "/sv/publicerat/rapporter/bolanerapport/",
            "/sv/publicerat/rapporter/fi-analys/",
            "/sv/publicerat/rapporter/bankbarometer/",
            "/sv/publicerat/rapporter/ovriga-rapporter/",
        ]

        all_report_links = []

        for category_path in report_categories:
            url = urljoin(BASE_URL, category_path)
            html = await self.fetch_page(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Find all PDF and document links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if any(ext in href.lower() for ext in [".pdf", "rapporter/", "rapport-"]):
                    full_url = urljoin(BASE_URL, href)
                    if full_url not in all_report_links:
                        all_report_links.append((full_url, category_path))

        logger.info(f"Found {len(all_report_links)} report links")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [self._scrape_report(url, cat, semaphore) for url, cat in all_report_links]

        await tqdm.gather(*tasks, desc="Reports")

    async def _scrape_report(self, url: str, category: str, semaphore: asyncio.Semaphore):
        """Scrape individual report"""
        async with semaphore:
            # Skip PDFs for now (would need PDF extraction library)
            if url.lower().endswith(".pdf"):
                logger.debug(f"Skipping PDF: {url}")
                return

            html = await self.fetch_page(url)
            if not html:
                return

            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled Report"

            # Extract date if available
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
            pub_date = date_match.group(1) if date_match else None

            metadata = {
                "source": SOURCE_NAME,
                "doc_type": "report",
                "category": category.split("/")[-2],
                "url": url,
            }
            if pub_date:
                metadata["publication_date"] = pub_date

            content = self.extract_text(soup)

            # Generate ID from URL
            doc_id = f"fi_report_{hash(url) & 0xFFFFFFFF:08x}"

            doc = Document(
                id=doc_id,
                title=title,
                url=url,
                content=content,
                doc_type="report",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["reports"] += 1
            self.stats["total"] += 1

    async def scrape_supervisory_decisions(self):
        """Scrape supervisory decisions"""
        logger.info("Scraping supervisory decisions...")

        decisions_urls = [
            "/sv/publicerat/granskningar/pagaende-undersokningar/",
            "/sv/publicerat/granskningar/avslutade-undersokningar/",
        ]

        all_links = []

        for path in decisions_urls:
            url = urljoin(BASE_URL, path)
            html = await self.fetch_page(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Find decision links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "granskningar/" in href and href != path:
                    full_url = urljoin(BASE_URL, href)
                    if full_url not in all_links:
                        all_links.append(full_url)

        logger.info(f"Found {len(all_links)} supervisory decision links")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [self._scrape_decision(url, semaphore) for url in all_links]

        await tqdm.gather(*tasks, desc="Supervisory decisions")

    async def _scrape_decision(self, url: str, semaphore: asyncio.Semaphore):
        """Scrape individual supervisory decision"""
        async with semaphore:
            html = await self.fetch_page(url)
            if not html:
                return

            soup = BeautifulSoup(html, "html.parser")

            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled Decision"

            metadata = {"source": SOURCE_NAME, "doc_type": "supervisory_decision", "url": url}

            # Look for date
            for elem in soup.find_all(["time", "span", "p"]):
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", elem.get_text())
                if date_match:
                    metadata["decision_date"] = date_match.group(1)
                    break

            content = self.extract_text(soup)

            doc_id = f"fi_decision_{hash(url) & 0xFFFFFFFF:08x}"

            doc = Document(
                id=doc_id,
                title=title,
                url=url,
                content=content,
                doc_type="supervisory_decision",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["supervisory_decisions"] += 1
            self.stats["total"] += 1

    async def scrape_all(self):
        """Run all scrapers"""
        logger.info("Starting FI document scrape...")

        await self.scrape_fffs_regulations()
        await self.scrape_reports()
        await self.scrape_supervisory_decisions()

        logger.info(f"Scraping complete. Total documents: {self.stats['total']}")

    def store_in_chromadb(self):
        """Store documents in ChromaDB"""
        logger.info("Storing documents in ChromaDB...")

        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        collection = client.get_or_create_collection(name=COLLECTION_NAME)

        # Prepare batch data with deduplication
        seen_ids = set()
        ids = []
        documents = []
        metadatas = []

        for doc in self.documents:
            if doc.id not in seen_ids:
                seen_ids.add(doc.id)
                ids.append(doc.id)
                documents.append(doc.content[:10000])  # Truncate if needed
                metadatas.append(doc.metadata)
            else:
                logger.debug(f"Skipping duplicate ID: {doc.id}")

        # Batch upsert
        if ids:
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
            logger.info(f"Stored {len(ids)} documents in ChromaDB")
        else:
            logger.warning("No documents to store")

    def generate_report(self) -> dict:
        """Generate JSON report"""
        report = {
            "source": SOURCE_NAME,
            "scraped_at": datetime.now().isoformat(),
            "stats": self.stats,
            "flag": self.stats["total"] < MIN_DOCS_THRESHOLD,
            "flag_reason": f"Below threshold ({self.stats['total']} < {MIN_DOCS_THRESHOLD})"
            if self.stats["total"] < MIN_DOCS_THRESHOLD
            else None,
            "errors": self.errors,
            "sample_documents": [asdict(doc) for doc in self.documents[:5]],
        }

        return report


async def main():
    async with FIScraper() as scraper:
        await scraper.scrape_all()

        # Store in ChromaDB
        scraper.store_in_chromadb()

        # Generate report
        report = scraper.generate_report()

        # Save report
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {OUTPUT_FILE}")

        # Print summary
        print("\n" + "=" * 60)
        print("FINANSINSPEKTIONEN SCRAPE COMPLETE")
        print("=" * 60)
        print(f"Total documents: {report['stats']['total']}")
        print(f"  - FFFS regulations: {report['stats']['fffs']}")
        print(f"  - Reports: {report['stats']['reports']}")
        print(f"  - Supervisory decisions: {report['stats']['supervisory_decisions']}")
        print(f"  - Errors: {report['stats']['errors']}")
        print(f"\nFlagged: {report['flag']}")
        if report["flag"]:
            print(f"Reason: {report['flag_reason']}")
        print(f"\nReport: {OUTPUT_FILE}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
