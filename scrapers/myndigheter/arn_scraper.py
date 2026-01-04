#!/usr/bin/env python3
"""
ARN (Allmänna reklamationsnämnden) Document Scraper
Targets: Decisions, Guidelines, Common cases (Vanliga fall), Annual reports
Stores in ChromaDB collection: swedish_gov_docs
"""

import asyncio
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import aiohttp
import chromadb
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm

# Configuration
BASE_URL = "https://www.arn.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "arn"
OUTPUT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/arn_scraper_report.json"
MIN_DOCS_THRESHOLD = 100
MAX_CONCURRENT = 10
TIMEOUT = 30

# Dispute areas
DISPUTE_AREAS = [
    "bank",
    "bostad",
    "bat",
    "elektronik",
    "forsakring",
    "motor",
    "mobler",
    "resor",
    "skor",
    "textilier",
    "tvatt",
    "ovrigt",
]

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """ARN document metadata"""

    id: str
    title: str
    url: str
    content: str
    doc_type: str  # common_case, annual_report, guideline, statistic
    metadata: dict
    scraped_at: str


class ARNScraper:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.documents: list[Document] = []
        self.errors: list[dict] = []
        self.stats = {
            "common_cases": 0,
            "annual_reports": 0,
            "guidelines": 0,
            "statistics": 0,
            "total": 0,
            "errors": 0,
        }
        self.scraped_urls = set()

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_page(self, url: str, retries: int = 3) -> Optional[str]:
        """Fetch a page with retry logic"""
        for attempt in range(retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status == 404:
                        logger.debug(f"404 Not Found: {url}")
                        return None
                    logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on {url} (attempt {attempt+1}/{retries})")
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

    async def scrape_common_cases(self):
        """Scrape common cases (Vanliga fall) from all dispute areas"""
        logger.info("Scraping common cases from all dispute areas...")

        all_case_links = []

        # Collect links from each dispute area
        for area in DISPUTE_AREAS:
            area_url = f"{BASE_URL}/tvisteomraden/{area}/"
            html = await self.fetch_page(area_url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Find all vanligafall links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/vanligafall/" in href:
                    full_url = urljoin(BASE_URL, href)
                    if full_url not in self.scraped_urls:
                        self.scraped_urls.add(full_url)
                        all_case_links.append((full_url, area))

        logger.info(f"Found {len(all_case_links)} common case links")

        # Fetch each case
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [self._scrape_common_case(url, area, semaphore) for url, area in all_case_links]

        await tqdm.gather(*tasks, desc="Common cases")

    async def _scrape_common_case(self, url: str, area: str, semaphore: asyncio.Semaphore):
        """Scrape individual common case"""
        async with semaphore:
            html = await self.fetch_page(url)
            if not html:
                return

            soup = BeautifulSoup(html, "html.parser")

            # Extract title
            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled Case"

            # Extract case number from URL
            case_number_match = re.search(r"/vanligafall/([\d\.]+)", url)
            case_number = case_number_match.group(1) if case_number_match else None

            # Extract metadata
            metadata = {
                "source": SOURCE_NAME,
                "doc_type": "common_case",
                "dispute_area": area,
                "url": url,
            }

            if case_number:
                metadata["case_number"] = case_number

            # Look for case outcome keywords
            content_text = soup.get_text().lower()
            if "nämnden anser" in content_text:
                metadata["has_decision"] = True
            if "konsumenten" in content_text and "fick rätt" in content_text:
                metadata["outcome_hint"] = "consumer_favor"
            elif "företaget" in content_text and "fick rätt" in content_text:
                metadata["outcome_hint"] = "company_favor"

            # Extract content
            content = self.extract_text(soup)

            # Generate ID
            doc_id = (
                f"arn_case_{case_number.replace('.', '_')}"
                if case_number
                else f"arn_case_{hash(url) & 0xFFFFFFFF:08x}"
            )

            doc = Document(
                id=doc_id,
                title=title,
                url=url,
                content=content,
                doc_type="common_case",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["common_cases"] += 1
            self.stats["total"] += 1

    async def scrape_annual_reports(self):
        """Scrape annual reports"""
        logger.info("Scraping annual reports...")

        reports_url = f"{BASE_URL}/om-arn/arsredovisning/"
        html = await self.fetch_page(reports_url)
        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        # Find all report links (PDFs and pages)
        report_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "arsredovisning" in href.lower() or ".pdf" in href.lower():
                full_url = urljoin(BASE_URL, href)
                if full_url not in self.scraped_urls:
                    self.scraped_urls.add(full_url)
                    report_links.append(full_url)

        logger.info(f"Found {len(report_links)} annual report links")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [self._scrape_annual_report(url, semaphore) for url in report_links]

        await tqdm.gather(*tasks, desc="Annual reports")

    async def _scrape_annual_report(self, url: str, semaphore: asyncio.Semaphore):
        """Scrape individual annual report"""
        async with semaphore:
            # Skip PDFs (would need extraction library)
            if url.lower().endswith(".pdf"):
                logger.debug(f"Skipping PDF: {url}")
                return

            html = await self.fetch_page(url)
            if not html:
                return

            soup = BeautifulSoup(html, "html.parser")

            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled Report"

            # Extract year from URL or title
            year_match = re.search(r"(20\d{2})", url + title)
            year = year_match.group(1) if year_match else None

            metadata = {"source": SOURCE_NAME, "doc_type": "annual_report", "url": url}

            if year:
                metadata["year"] = year

            content = self.extract_text(soup)

            doc_id = f"arn_report_{year}" if year else f"arn_report_{hash(url) & 0xFFFFFFFF:08x}"

            doc = Document(
                id=doc_id,
                title=title,
                url=url,
                content=content,
                doc_type="annual_report",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["annual_reports"] += 1
            self.stats["total"] += 1

    async def scrape_statistics(self):
        """Scrape statistics page"""
        logger.info("Scraping statistics...")

        stats_url = f"{BASE_URL}/om-arn/statistik/"
        html = await self.fetch_page(stats_url)
        if not html:
            return

        soup = BeautifulSoup(html, "html.parser")

        title = "ARN Statistics"
        content = self.extract_text(soup)

        metadata = {"source": SOURCE_NAME, "doc_type": "statistic", "url": stats_url}

        # Extract year from content
        year_match = re.search(r"(20\d{2})", content)
        if year_match:
            metadata["latest_year"] = year_match.group(1)

        doc = Document(
            id="arn_statistics",
            title=title,
            url=stats_url,
            content=content,
            doc_type="statistic",
            metadata=metadata,
            scraped_at=datetime.now().isoformat(),
        )

        self.documents.append(doc)
        self.stats["statistics"] += 1
        self.stats["total"] += 1

    async def scrape_guidelines(self):
        """Scrape guidelines and FAQ"""
        logger.info("Scraping guidelines and FAQ...")

        guideline_paths = [
            "/konsument/fragor-och-svar/",
            "/om-arn/ordlista/",
            "/om-arn/vart-serviceatagande/",
            "/konsument/",
            "/foretag/",
        ]

        for path in guideline_paths:
            url = urljoin(BASE_URL, path)
            if url in self.scraped_urls:
                continue

            self.scraped_urls.add(url)

            html = await self.fetch_page(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else path.split("/")[-2]

            metadata = {
                "source": SOURCE_NAME,
                "doc_type": "guideline",
                "url": url,
                "section": path.split("/")[-2],
            }

            content = self.extract_text(soup)

            doc_id = f"arn_guideline_{path.split('/')[-2]}"

            doc = Document(
                id=doc_id,
                title=title,
                url=url,
                content=content,
                doc_type="guideline",
                metadata=metadata,
                scraped_at=datetime.now().isoformat(),
            )

            self.documents.append(doc)
            self.stats["guidelines"] += 1
            self.stats["total"] += 1

    async def scrape_all(self):
        """Run all scrapers"""
        logger.info("Starting ARN document scrape...")

        await self.scrape_common_cases()
        await self.scrape_annual_reports()
        await self.scrape_statistics()
        await self.scrape_guidelines()

        logger.info(f"Scraping complete. Total documents: {self.stats['total']}")

    def store_in_chromadb(self):
        """Store documents in ChromaDB"""
        logger.info("Storing documents in ChromaDB...")

        try:
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
        except Exception as e:
            logger.error(f"ChromaDB storage failed: {e}")
            logger.info("Documents saved to JSON report instead")

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
            "all_documents": [asdict(doc) for doc in self.documents],
        }

        return report


async def main():
    async with ARNScraper() as scraper:
        await scraper.scrape_all()

        # Generate report (before ChromaDB to ensure it's saved)
        report = scraper.generate_report()

        # Save report
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {OUTPUT_FILE}")

        # Store in ChromaDB (may crash, but report is already saved)
        scraper.store_in_chromadb()

        # Print summary
        print("\n" + "=" * 60)
        print("ARN SCRAPE COMPLETE")
        print("=" * 60)
        print(f"Total documents: {report['stats']['total']}")
        print(f"  - Common cases: {report['stats']['common_cases']}")
        print(f"  - Annual reports: {report['stats']['annual_reports']}")
        print(f"  - Statistics: {report['stats']['statistics']}")
        print(f"  - Guidelines: {report['stats']['guidelines']}")
        print(f"  - Errors: {report['stats']['errors']}")
        print(f"\nFlagged: {report['flag']}")
        if report["flag"]:
            print(f"Reason: {report['flag_reason']}")
        print(f"\nReport: {OUTPUT_FILE}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
