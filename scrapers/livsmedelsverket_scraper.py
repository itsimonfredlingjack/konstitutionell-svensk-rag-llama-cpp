#!/usr/bin/env python3
"""
Livsmedelsverket Document Scraper
Scrapes LIVSFS regulations, reports, guidelines, and control results.
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import chromadb
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class Document:
    """Represents a Livsmedelsverket document"""

    url: str
    title: str
    doc_type: str  # LIVSFS, rapport, vägledning, kontroll
    content: str
    published_date: Optional[str] = None
    document_id: Optional[str] = None
    metadata: Optional[dict] = None

    def to_dict(self):
        return asdict(self)

    def get_hash(self) -> str:
        """Generate unique hash for deduplication"""
        content = f"{self.url}|{self.title}|{self.doc_type}"
        return hashlib.sha256(content.encode()).hexdigest()


class LivesmedelsverketScraper:
    """Scraper for livsmedelsverket.se documents"""

    BASE_URL = "https://www.livsmedelsverket.se"

    # Document type endpoints (based on actual site structure)
    ENDPOINTS = {
        "LIVSFS": "/om-oss/lagstiftning1/gallande-lagstiftning",
        "lagstiftning": "/om-oss/lagstiftning1",
        "vagledningar": "/foretagande-regler-kontroll/vagledning-till-lagstiftningen",
        "kontroll": "/foretagande-regler-kontroll/sa-kontrolleras-ditt-foretag",
    }

    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
        collection_name: str = "swedish_gov_docs",
        max_concurrent: int = 10,
        delay: float = 0.5,
    ):
        self.chromadb_path = chromadb_path
        self.collection_name = collection_name
        self.max_concurrent = max_concurrent
        self.delay = delay

        self.ua = UserAgent()
        self.session: Optional[aiohttp.ClientSession] = None
        self.documents: list[Document] = []
        self.seen_urls: set[str] = set()
        self.errors: list[dict] = []

        # Stats
        self.stats = {
            "total_pages_visited": 0,
            "total_docs_found": 0,
            "total_docs_stored": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
        }

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": self.ua.random}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch(self, url: str) -> Optional[str]:
        """Fetch URL with retries"""
        for attempt in range(3):
            try:
                await asyncio.sleep(self.delay)
                async with self.session.get(url) as response:
                    if response.status == 200:
                        self.stats["total_pages_visited"] += 1
                        return await response.text()
                    elif response.status == 404:
                        logger.warning(f"404 Not Found: {url}")
                        return None
                    else:
                        logger.warning(f"Status {response.status} for {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout attempt {attempt+1}/3 for {url}")
                await asyncio.sleep(2**attempt)
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                self.errors.append({"url": url, "error": str(e)})
                self.stats["errors"] += 1
                return None
        return None

    def extract_date(self, text: str) -> Optional[str]:
        """Extract date from text"""
        patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}\s+\w+\s+\d{4}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    async def scrape_livsfs(self) -> list[Document]:
        """Scrape LIVSFS regulations - now with deep crawling"""
        url = urljoin(self.BASE_URL, self.ENDPOINTS["LIVSFS"])
        logger.info(f"Scraping LIVSFS from {url}")

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        documents = []

        # First find all year-specific pages
        all_links = soup.find_all("a", href=True)
        year_pages = []

        for link in all_links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            # Match year patterns like "2024", "2023", etc.
            if re.search(r"20\d{2}", text) and "nummerordning" in href:
                year_pages.append(urljoin(self.BASE_URL, href))

        logger.info(f"Found {len(year_pages)} year pages to crawl")

        # Crawl each year page for individual LIVSFS documents
        livsfs_links = []
        for year_page in year_pages[:10]:  # Limit years to prevent overwhelming
            if year_page in self.seen_urls:
                continue
            self.seen_urls.add(year_page)

            year_html = await self.fetch(year_page)
            if not year_html:
                continue

            year_soup = BeautifulSoup(year_html, "html.parser")
            year_links = year_soup.find_all("a", href=True)

            for link in year_links:
                href = link.get("href", "")
                text = link.get_text(strip=True)
                # Look for individual LIVSFS documents
                if "livsfs-" in href.lower() or re.search(r"LIVSFS\s*\d{4}:\d+", text):
                    livsfs_links.append(link)

        # Also look for PDF links in globalassets
        pdf_links = soup.find_all("a", href=re.compile(r"globalassets.*livsfs.*\.pdf"))
        livsfs_links.extend(pdf_links)

        logger.info(f"Found {len(livsfs_links)} total LIVSFS document links")

        for link in livsfs_links[:200]:  # Increased limit for regulations
            href = link.get("href")
            if not href:
                continue

            full_url = urljoin(self.BASE_URL, href)
            if full_url in self.seen_urls:
                continue
            self.seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                # Try to extract from parent or URL
                parent = link.find_parent(["li", "div", "td"])
                if parent:
                    title = parent.get_text(strip=True)[:200]
                if not title:
                    title = Path(urlparse(href).path).stem

            # Handle PDFs
            if href.endswith(".pdf"):
                content = f"PDF Regulation Document\nTitle: {title}\nURL: {full_url}"
                doc_id_match = re.search(r"livsfs[-_]?(\d{4}[-:]?\d+)", href, re.I)
                if doc_id_match:
                    doc_id = f"LIVSFS {doc_id_match.group(1).replace('-', ':')}"
                else:
                    doc_id = Path(urlparse(full_url).path).stem
            else:
                # Fetch HTML document
                doc_html = await self.fetch(full_url)
                if not doc_html:
                    continue

                doc_soup = BeautifulSoup(doc_html, "html.parser")

                # Extract main content
                content_div = (
                    doc_soup.find("main")
                    or doc_soup.find("article")
                    or doc_soup.find("div", class_=re.compile(r"content|main"))
                )
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = doc_soup.get_text(separator="\n", strip=True)[:5000]

                # Extract doc ID
                doc_id_match = re.search(r"LIVSFS\s+\d{4}:\d+", title + " " + content[:1000])
                if doc_id_match:
                    doc_id = doc_id_match.group(0)
                else:
                    doc_id = Path(urlparse(full_url).path).stem

            pub_date = self.extract_date(title + " " + content[:1000])

            doc = Document(
                url=full_url,
                title=title,
                doc_type="LIVSFS",
                content=content[:10000],
                published_date=pub_date,
                document_id=doc_id,
                metadata={"source": "livsmedelsverket"},
            )

            documents.append(doc)
            logger.info(f"Scraped LIVSFS: {title[:60]}")

        return documents

    async def scrape_lagstiftning(self) -> list[Document]:
        """Scrape general legislation pages"""
        url = urljoin(self.BASE_URL, self.ENDPOINTS["lagstiftning"])
        logger.info(f"Scraping lagstiftning from {url}")

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        documents = []

        # Find all content links
        all_links = soup.find_all("a", href=True)

        # Filter for legislation-related content
        content_links = []
        for link in all_links:
            href = link.get("href", "")
            if any(
                keyword in href.lower() for keyword in ["lagstiftning", "foreskrift", "gallande"]
            ):
                content_links.append(link)

        logger.info(f"Found {len(content_links)} lagstiftning links")

        for link in content_links[:100]:
            href = link.get("href")
            if not href:
                continue

            full_url = urljoin(self.BASE_URL, href)
            if full_url in self.seen_urls:
                continue
            self.seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                parent = link.find_parent(["li", "div", "td"])
                if parent:
                    title = parent.get_text(strip=True)[:200]
                if not title:
                    title = Path(urlparse(href).path).stem

            # Fetch content
            doc_html = await self.fetch(full_url)
            if not doc_html:
                continue

            doc_soup = BeautifulSoup(doc_html, "html.parser")
            content_div = doc_soup.find("main") or doc_soup.find("article")
            if content_div:
                content = content_div.get_text(separator="\n", strip=True)
            else:
                content = doc_soup.get_text(separator="\n", strip=True)[:5000]

            pub_date = self.extract_date(content[:1000])

            doc = Document(
                url=full_url,
                title=title,
                doc_type="lagstiftning",
                content=content[:10000],
                published_date=pub_date,
                document_id=Path(urlparse(full_url).path).stem,
                metadata={"source": "livsmedelsverket"},
            )

            documents.append(doc)
            logger.info(f"Scraped lagstiftning: {title[:50]}")

        return documents

    async def scrape_vagledningar(self) -> list[Document]:
        """Scrape guidelines"""
        url = urljoin(self.BASE_URL, self.ENDPOINTS["vagledningar"])
        logger.info(f"Scraping vägledningar from {url}")

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        documents = []

        links = soup.find_all("a", href=True)
        logger.info(f"Found {len(links)} potential vägledning links")

        for link in links[:100]:
            href = link.get("href")
            if not href or "vagledning" not in href.lower():
                continue

            full_url = urljoin(self.BASE_URL, href)
            if full_url in self.seen_urls:
                continue
            self.seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            doc_html = await self.fetch(full_url)
            if not doc_html:
                continue

            doc_soup = BeautifulSoup(doc_html, "html.parser")
            content_div = doc_soup.find("main") or doc_soup.find("article")
            if content_div:
                content = content_div.get_text(separator="\n", strip=True)
            else:
                content = doc_soup.get_text(separator="\n", strip=True)[:5000]

            doc = Document(
                url=full_url,
                title=title,
                doc_type="vägledning",
                content=content[:10000],
                published_date=self.extract_date(content[:1000]),
                document_id=Path(urlparse(full_url).path).stem,
                metadata={"source": "livsmedelsverket"},
            )

            documents.append(doc)
            logger.info(f"Scraped vägledning: {title[:50]}")

        return documents

    async def scrape_kontroll(self) -> list[Document]:
        """Scrape control results"""
        url = urljoin(self.BASE_URL, self.ENDPOINTS["kontroll"])
        logger.info(f"Scraping kontrollresultat from {url}")

        html = await self.fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        documents = []

        links = soup.find_all("a", href=True)
        logger.info(f"Found {len(links)} potential kontroll links")

        for link in links[:100]:
            href = link.get("href")
            if not href or "kontroll" not in href.lower():
                continue

            full_url = urljoin(self.BASE_URL, href)
            if full_url in self.seen_urls:
                continue
            self.seen_urls.add(full_url)

            title = link.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            doc_html = await self.fetch(full_url)
            if not doc_html:
                continue

            doc_soup = BeautifulSoup(doc_html, "html.parser")
            content_div = doc_soup.find("main") or doc_soup.find("article")
            if content_div:
                content = content_div.get_text(separator="\n", strip=True)
            else:
                content = doc_soup.get_text(separator="\n", strip=True)[:5000]

            doc = Document(
                url=full_url,
                title=title,
                doc_type="kontroll",
                content=content[:10000],
                published_date=self.extract_date(content[:1000]),
                document_id=Path(urlparse(full_url).path).stem,
                metadata={"source": "livsmedelsverket"},
            )

            documents.append(doc)
            logger.info(f"Scraped kontroll: {title[:50]}")

        return documents

    async def scrape_all(self) -> list[Document]:
        """Scrape all document types"""
        self.stats["start_time"] = datetime.now().isoformat()

        logger.info("Starting Livsmedelsverket scrape...")

        # Run all scrapers
        results = await asyncio.gather(
            self.scrape_livsfs(),
            self.scrape_lagstiftning(),
            self.scrape_vagledningar(),
            self.scrape_kontroll(),
            return_exceptions=True,
        )

        # Flatten results
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Scraper error: {result}")
                self.stats["errors"] += 1
            elif isinstance(result, list):
                self.documents.extend(result)

        self.stats["total_docs_found"] = len(self.documents)
        self.stats["end_time"] = datetime.now().isoformat()

        logger.info(f"Scraping complete. Found {len(self.documents)} documents.")

        return self.documents

    def store_in_chromadb(self) -> int:
        """Store documents in ChromaDB"""
        if not self.documents:
            logger.warning("No documents to store")
            return 0

        logger.info(f"Storing {len(self.documents)} documents in ChromaDB...")

        try:
            client = chromadb.PersistentClient(path=self.chromadb_path)
            collection = client.get_or_create_collection(name=self.collection_name)

            stored_count = 0
            batch_size = 100

            for i in range(0, len(self.documents), batch_size):
                batch = self.documents[i : i + batch_size]

                ids = [doc.get_hash() for doc in batch]
                documents = [doc.content for doc in batch]
                metadatas = [
                    {
                        "source": "livsmedelsverket",
                        "doc_type": doc.doc_type,
                        "title": doc.title,
                        "url": doc.url,
                        "published_date": doc.published_date or "unknown",
                        "document_id": doc.document_id or "unknown",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    for doc in batch
                ]

                collection.add(ids=ids, documents=documents, metadatas=metadatas)

                stored_count += len(batch)
                logger.info(
                    f"Stored batch {i//batch_size + 1}: {stored_count}/{len(self.documents)}"
                )

            self.stats["total_docs_stored"] = stored_count
            logger.info(f"Successfully stored {stored_count} documents in ChromaDB")

            return stored_count

        except Exception as e:
            logger.error(f"Error storing in ChromaDB: {e}")
            self.stats["errors"] += 1
            raise

    def generate_report(self) -> dict:
        """Generate final report"""
        duration = None
        if self.stats["start_time"] and self.stats["end_time"]:
            start = datetime.fromisoformat(self.stats["start_time"])
            end = datetime.fromisoformat(self.stats["end_time"])
            duration = (end - start).total_seconds()

        doc_types = {}
        for doc in self.documents:
            doc_types[doc.doc_type] = doc_types.get(doc.doc_type, 0) + 1

        report = {
            "source": "livsmedelsverket",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": duration,
            "statistics": {
                "total_pages_visited": self.stats["total_pages_visited"],
                "total_docs_found": self.stats["total_docs_found"],
                "total_docs_stored": self.stats["total_docs_stored"],
                "errors": self.stats["errors"],
                "doc_types": doc_types,
            },
            "flag_warning": self.stats["total_docs_stored"] < 100,
            "errors": self.errors[:10],  # First 10 errors
        }

        return report


async def main():
    """Main execution"""
    async with LivesmedelsverketScraper() as scraper:
        # Scrape all documents
        documents = await scraper.scrape_all()

        # Store in ChromaDB
        if documents:
            scraper.store_in_chromadb()

        # Generate report
        report = scraper.generate_report()

        # Save report
        report_path = Path(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/livsmedelsverket_report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {report_path}")

        # Print summary
        print("\n" + "=" * 60)
        print("LIVSMEDELSVERKET SCRAPE REPORT")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("=" * 60)

        if report["flag_warning"]:
            print("\n⚠️  WARNING: Less than 100 documents found!")

        return report


if __name__ == "__main__":
    asyncio.run(main())
