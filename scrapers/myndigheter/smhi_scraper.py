#!/usr/bin/env python3
"""
SMHI Document Scraper
=====================
Scrapes climate reports, forecasts, regulations, and research data from SMHI.

Target: smhi.se
Collection: swedish_gov_docs
Source metadata: "smhi"
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "smhi"
BASE_URL = "https://www.smhi.se"
MIN_DOCUMENTS_THRESHOLD = 100

# Request configuration
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 1.0  # seconds between requests

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SMHIScraper:
    """Scraper for SMHI documents and publications."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.visited_urls: set[str] = set()
        self.documents: list[dict] = []
        self.errors: list[dict] = []

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
        )

    def fetch_url(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a URL."""
        if url in self.visited_urls:
            return None

        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self.visited_urls.add(url)
            time.sleep(REQUEST_DELAY)
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.errors.append(
                {"url": url, "error": str(e), "timestamp": datetime.now().isoformat()}
            )
            return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content from page."""
        # Remove script, style, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Try to find main content area
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|main", re.I))
            or soup.find("body")
        )

        if main_content:
            text = main_content.get_text(separator=" ", strip=True)
            # Clean up whitespace
            text = re.sub(r"\s+", " ", text)
            return text.strip()
        return ""

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract metadata from page."""
        metadata = {
            "source": SOURCE_NAME,
            "url": url,
            "scraped_at": datetime.now().isoformat(),
        }

        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.text.strip()

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            metadata["description"] = meta_desc["content"].strip()

        # Date (try various patterns)
        date_patterns = [
            soup.find("time"),
            soup.find("meta", attrs={"property": "article:published_time"}),
            soup.find("span", class_=re.compile(r"date|published", re.I)),
        ]

        for pattern in date_patterns:
            if pattern:
                date_str = pattern.get("datetime") or pattern.text
                if date_str:
                    metadata["published_date"] = date_str.strip()
                    break

        # Document type (inferred from URL)
        if "/publikationer/" in url:
            metadata["doc_type"] = "publikation"
        elif "/kunskapsbanken/" in url:
            metadata["doc_type"] = "kunskapsbank"
        elif "/klimat" in url:
            metadata["doc_type"] = "klimatrapport"
        elif "/vader" in url:
            metadata["doc_type"] = "vaderprognos"
        else:
            metadata["doc_type"] = "general"

        return metadata

    def scrape_publications_search(self) -> None:
        """Scrape publications using search API if available."""
        logger.info("Attempting to scrape publications...")

        # Try to access publication search/listing pages
        pub_urls = [
            f"{BASE_URL}/publikationer",
            f"{BASE_URL}/publikationer/publikationer",
            f"{BASE_URL}/publikationer/rapporter",
        ]

        for url in pub_urls:
            soup = self.fetch_url(url)
            if not soup:
                continue

            # Look for PDF links
            pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
            for link in pdf_links:
                href = link.get("href")
                if href:
                    pdf_url = urljoin(url, href)
                    self.process_pdf(pdf_url, link.text.strip())

            # Look for publication links
            pub_links = soup.find_all("a", href=re.compile(r"/publikationer/", re.I))
            for link in pub_links[:50]:  # Limit to avoid infinite loops
                href = link.get("href")
                if href:
                    pub_url = urljoin(url, href)
                    self.scrape_publication_page(pub_url)

    def scrape_publication_page(self, url: str) -> None:
        """Scrape a single publication page."""
        soup = self.fetch_url(url)
        if not soup:
            return

        text_content = self.extract_text_content(soup)
        if not text_content or len(text_content) < 100:
            return

        metadata = self.extract_metadata(soup, url)

        # Check for PDF download link
        pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
        if pdf_link:
            metadata["pdf_url"] = urljoin(url, pdf_link.get("href"))

        self.documents.append({"text": text_content, "metadata": metadata})

        logger.info(f"Scraped publication: {metadata.get('title', url)}")

    def process_pdf(self, pdf_url: str, title: str = "") -> None:
        """Process a PDF document."""
        if pdf_url in self.visited_urls:
            return

        try:
            logger.info(f"Processing PDF: {pdf_url}")
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            self.visited_urls.add(pdf_url)

            # Store PDF metadata (actual PDF parsing would require PyPDF2/pdfplumber)
            metadata = {
                "source": SOURCE_NAME,
                "url": pdf_url,
                "title": title or pdf_url.split("/")[-1],
                "doc_type": "pdf",
                "scraped_at": datetime.now().isoformat(),
                "file_size": len(response.content),
            }

            # Store basic info (without full text extraction for now)
            self.documents.append(
                {"text": f"PDF Document: {title or pdf_url}", "metadata": metadata}
            )

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.error(f"Error processing PDF {pdf_url}: {e}")
            self.errors.append(
                {"url": pdf_url, "error": str(e), "timestamp": datetime.now().isoformat()}
            )

    def scrape_knowledge_bank(self) -> None:
        """Scrape knowledge bank articles."""
        logger.info("Scraping knowledge bank...")

        base_url = f"{BASE_URL}/kunskapsbanken"
        soup = self.fetch_url(base_url)
        if not soup:
            return

        # Find article links
        article_links = soup.find_all("a", href=re.compile(r"/kunskapsbanken/", re.I))

        for link in article_links[:100]:  # Limit
            href = link.get("href")
            if href and href not in self.visited_urls:
                article_url = urljoin(base_url, href)
                self.scrape_article(article_url)

    def scrape_article(self, url: str) -> None:
        """Scrape a knowledge bank article."""
        soup = self.fetch_url(url)
        if not soup:
            return

        text_content = self.extract_text_content(soup)
        if not text_content or len(text_content) < 100:
            return

        metadata = self.extract_metadata(soup, url)

        self.documents.append({"text": text_content, "metadata": metadata})

        logger.info(f"Scraped article: {metadata.get('title', url)}")

    def scrape_climate_pages(self) -> None:
        """Scrape climate-related pages."""
        logger.info("Scraping climate pages...")

        climate_urls = [
            f"{BASE_URL}/klimat",
            f"{BASE_URL}/klimat/klimatet-i-sverige",
            f"{BASE_URL}/klimat/klimatscenarier",
            f"{BASE_URL}/klimat/framtidens-klimat",
        ]

        for url in climate_urls:
            soup = self.fetch_url(url)
            if not soup:
                continue

            text_content = self.extract_text_content(soup)
            if text_content and len(text_content) >= 100:
                metadata = self.extract_metadata(soup, url)
                metadata["category"] = "klimat"

                self.documents.append({"text": text_content, "metadata": metadata})

                logger.info(f"Scraped climate page: {metadata.get('title', url)}")

            # Find related links
            related_links = soup.find_all("a", href=re.compile(r"/klimat/", re.I))
            for link in related_links[:20]:
                href = link.get("href")
                if href and href not in self.visited_urls:
                    related_url = urljoin(url, href)
                    related_soup = self.fetch_url(related_url)
                    if related_soup:
                        related_text = self.extract_text_content(related_soup)
                        if related_text and len(related_text) >= 100:
                            related_metadata = self.extract_metadata(related_soup, related_url)
                            related_metadata["category"] = "klimat"
                            self.documents.append(
                                {"text": related_text, "metadata": related_metadata}
                            )

    def save_to_chromadb(self) -> int:
        """Save scraped documents to ChromaDB."""
        if not self.documents:
            logger.warning("No documents to save")
            return 0

        logger.info(f"Saving {len(self.documents)} documents to ChromaDB...")

        saved_count = 0
        for i, doc in enumerate(self.documents):
            try:
                doc_id = f"smhi_{int(time.time())}_{i}"

                self.collection.add(
                    documents=[doc["text"]], metadatas=[doc["metadata"]], ids=[doc_id]
                )
                saved_count += 1

            except Exception as e:
                logger.error(f"Error saving document {i}: {e}")
                self.errors.append(
                    {"document_index": i, "error": str(e), "timestamp": datetime.now().isoformat()}
                )

        logger.info(f"Saved {saved_count}/{len(self.documents)} documents to ChromaDB")
        return saved_count

    def generate_report(self, saved_count: int) -> dict:
        """Generate JSON report."""
        total_docs = len(self.documents)
        flagged = total_docs < MIN_DOCUMENTS_THRESHOLD

        report = {
            "scraper": "SMHI",
            "source": SOURCE_NAME,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_scraped": total_docs,
                "saved_to_chromadb": saved_count,
                "errors": len(self.errors),
                "urls_visited": len(self.visited_urls),
                "flagged": flagged,
                "flag_reason": f"Below threshold of {MIN_DOCUMENTS_THRESHOLD} documents"
                if flagged
                else None,
            },
            "collection": {
                "name": COLLECTION_NAME,
                "path": CHROMADB_PATH,
                "total_count": self.collection.count(),
            },
            "document_types": self._count_by_type(),
            "errors": self.errors[:20],  # Limit error list
            "sample_documents": [
                {
                    "title": doc["metadata"].get("title", "N/A"),
                    "url": doc["metadata"]["url"],
                    "doc_type": doc["metadata"].get("doc_type", "unknown"),
                    "text_length": len(doc["text"]),
                }
                for doc in self.documents[:10]
            ],
        }

        return report

    def _count_by_type(self) -> dict[str, int]:
        """Count documents by type."""
        type_counts = {}
        for doc in self.documents:
            doc_type = doc["metadata"].get("doc_type", "unknown")
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        return type_counts

    def run(self) -> dict:
        """Run the complete scraping process."""
        logger.info("=" * 60)
        logger.info("SMHI SCRAPER - START")
        logger.info("=" * 60)

        start_time = time.time()

        try:
            # Scrape different sections
            self.scrape_publications_search()
            self.scrape_knowledge_bank()
            self.scrape_climate_pages()

            # Save to ChromaDB
            saved_count = self.save_to_chromadb()

            # Generate report
            report = self.generate_report(saved_count)
            report["execution_time_seconds"] = round(time.time() - start_time, 2)

            # Save report
            report_path = Path(
                "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/smhi_scraper_report.json"
            )
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.info("=" * 60)
            logger.info("SMHI SCRAPER - COMPLETE")
            logger.info(f"Documents scraped: {report['summary']['total_scraped']}")
            logger.info(f"Documents saved: {report['summary']['saved_to_chromadb']}")
            logger.info(f"Flagged: {report['summary']['flagged']}")
            logger.info(f"Report saved: {report_path}")
            logger.info("=" * 60)

            return report

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            return {
                "scraper": "SMHI",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "status": "failed",
            }


def main():
    """Main entry point."""
    scraper = SMHIScraper()
    report = scraper.run()

    # Print summary
    print("\n" + "=" * 60)
    print("SCRAPER REPORT")
    print("=" * 60)
    print(json.dumps(report, indent=2, ensure_ascii=False))

    return report


if __name__ == "__main__":
    main()
