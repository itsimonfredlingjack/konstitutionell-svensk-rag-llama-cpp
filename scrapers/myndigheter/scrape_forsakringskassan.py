#!/usr/bin/env python3
"""
Försäkringskassan Document Scraper
Scrapes all public documents from forsakringskassan.se and indexes to ChromaDB

Usage:
    python scrape_forsakringskassan.py
"""

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import chromadb
import PyPDF2
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings
from tqdm import tqdm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/forsakringskassan_scrape.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://www.forsakringskassan.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
TEMP_DOWNLOAD_DIR = "/tmp/forsakringskassan_docs"
MIN_EXPECTED_DOCS = 100

# Ensure temp directory exists
Path(TEMP_DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

# User agent to avoid blocking
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}


class ForsakringskassanScraper:
    """Scraper for Försäkringskassan documents"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.documents: list[dict] = []
        self.failed_downloads: list[dict] = []
        self.processed_urls: set[str] = set()

        # Initialize ChromaDB
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.chroma_client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )
            logger.info(f"ChromaDB initialized at {CHROMADB_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise

    def fetch_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage with retries"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{retries} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None

    def download_pdf(self, url: str, filename: str) -> Optional[str]:
        """Download PDF and return local path"""
        try:
            response = self.session.get(url, timeout=60, stream=True)
            response.raise_for_status()

            filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug(f"Downloaded: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None

    def extract_pdf_text(self, filepath: str, max_pages: int = 50) -> str:
        """Extract text from PDF (limit pages to avoid memory issues)"""
        try:
            with open(filepath, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = min(len(reader.pages), max_pages)

                text_parts = []
                for page_num in range(num_pages):
                    page = reader.pages[page_num]
                    text_parts.append(page.extract_text())

                full_text = "\n\n".join(text_parts)

                if len(reader.pages) > max_pages:
                    full_text += f"\n\n[... {len(reader.pages) - max_pages} additional pages not extracted ...]"

                return full_text
        except Exception as e:
            logger.error(f"Failed to extract text from {filepath}: {e}")
            return ""

    def scrape_publications_page(self) -> list[dict]:
        """Scrape main publications page"""
        url = f"{BASE_URL}/om-forsakringskassan/publikationer"
        logger.info(f"Scraping publications page: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return []

        documents = []

        # Find all PDF links
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Skip if not a PDF or already processed
            if not href.endswith(".pdf") and "/download/" not in href:
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in self.processed_urls:
                continue

            self.processed_urls.add(full_url)

            # Extract metadata
            title = link.get_text(strip=True)

            # Try to find document type and year from surrounding context
            doc_type = "publikation"
            year = None

            parent = link.find_parent(["li", "div", "section"])
            if parent:
                parent_text = parent.get_text()

                # Identify document type
                if "rapport" in parent_text.lower():
                    doc_type = "rapport"
                elif "vägledning" in parent_text.lower():
                    doc_type = "vägledning"
                elif "ställningstagande" in parent_text.lower():
                    doc_type = "ställningstagande"
                elif "regeringsuppdrag" in parent_text.lower():
                    doc_type = "regeringsuppdrag"
                elif "statistik" in parent_text.lower() or "siffror" in parent_text.lower():
                    doc_type = "statistik"

                # Extract year
                import re

                year_match = re.search(r"(19|20)\d{2}", parent_text)
                if year_match:
                    year = year_match.group(0)

            documents.append(
                {
                    "url": full_url,
                    "title": title or os.path.basename(urlparse(full_url).path),
                    "type": doc_type,
                    "year": year,
                    "source_page": url,
                }
            )

        logger.info(f"Found {len(documents)} documents on publications page")
        return documents

    def scrape_statistics_page(self) -> list[dict]:
        """Scrape statistics and analysis page"""
        url = f"{BASE_URL}/statistik-och-analys"
        logger.info(f"Scraping statistics page: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return []

        documents = []

        # Find all PDF links
        for link in soup.find_all("a", href=True):
            href = link["href"]

            if not href.endswith(".pdf") and "/download/" not in href:
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in self.processed_urls:
                continue

            self.processed_urls.add(full_url)

            title = link.get_text(strip=True)

            # Extract file size if available
            file_size = None
            parent = link.find_parent(["li", "div"])
            if parent:
                import re

                size_match = re.search(r"(\d+)\s*(kB|MB)", parent.get_text())
                if size_match:
                    file_size = size_match.group(0)

                # Extract year
                year_match = re.search(r"(19|20)\d{2}", parent.get_text())
                year = year_match.group(0) if year_match else None

            documents.append(
                {
                    "url": full_url,
                    "title": title or os.path.basename(urlparse(full_url).path),
                    "type": "statistik",
                    "year": year,
                    "file_size": file_size,
                    "source_page": url,
                }
            )

        logger.info(f"Found {len(documents)} documents on statistics page")
        return documents

    def scrape_forms_page(self) -> list[dict]:
        """Scrape forms and information materials"""
        url = f"{BASE_URL}/privatperson/e-tjanster-blanketter-och-informationsmaterial"
        logger.info(f"Scraping forms page: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return []

        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if not href.endswith(".pdf") and "/download/" not in href:
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in self.processed_urls:
                continue

            self.processed_urls.add(full_url)

            title = link.get_text(strip=True)

            documents.append(
                {
                    "url": full_url,
                    "title": title or os.path.basename(urlparse(full_url).path),
                    "type": "blankett",
                    "year": None,
                    "source_page": url,
                }
            )

        logger.info(f"Found {len(documents)} documents on forms page")
        return documents

    def process_document(self, doc: dict) -> bool:
        """Download, extract, and index a single document"""
        try:
            url = doc["url"]
            filename = hashlib.md5(url.encode()).hexdigest() + ".pdf"

            # Download PDF
            filepath = self.download_pdf(url, filename)
            if not filepath:
                self.failed_downloads.append({**doc, "error": "Download failed"})
                return False

            # Extract text
            text = self.extract_pdf_text(filepath)
            if not text or len(text) < 100:
                logger.warning(f"Minimal text extracted from {doc['title']}")
                text = f"[Document: {doc['title']}]\n\nText extraction failed or minimal content."

            # Create document ID
            doc_id = hashlib.sha256(url.encode()).hexdigest()

            # Prepare metadata
            metadata = {
                "source": "forsakringskassan",
                "url": url,
                "title": doc["title"],
                "type": doc.get("type", "okänd"),
                "scraped_at": datetime.now().isoformat(),
                "source_page": doc.get("source_page", ""),
            }

            if doc.get("year"):
                metadata["year"] = doc["year"]
            if doc.get("file_size"):
                metadata["file_size"] = doc["file_size"]

            # Add to ChromaDB
            self.collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])

            # Cleanup temp file
            try:
                os.remove(filepath)
            except:
                pass

            logger.info(f"Indexed: {doc['title']}")
            return True

        except Exception as e:
            logger.error(f"Failed to process {doc.get('title', 'unknown')}: {e}")
            self.failed_downloads.append({**doc, "error": str(e)})
            return False

    def run(self) -> dict:
        """Execute full scrape and return report"""
        start_time = time.time()
        logger.info("Starting Försäkringskassan scrape")

        # Scrape all pages
        all_docs = []
        all_docs.extend(self.scrape_publications_page())
        time.sleep(1)  # Be nice to the server
        all_docs.extend(self.scrape_statistics_page())
        time.sleep(1)
        all_docs.extend(self.scrape_forms_page())

        logger.info(f"Total documents found: {len(all_docs)}")

        # Process documents with progress bar
        successful = 0
        for doc in tqdm(all_docs, desc="Processing documents"):
            if self.process_document(doc):
                successful += 1
            time.sleep(0.5)  # Rate limiting

        # Generate report
        elapsed = time.time() - start_time
        report = {
            "source": "forsakringskassan",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(elapsed, 2),
            "total_found": len(all_docs),
            "successful": successful,
            "failed": len(self.failed_downloads),
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "failed_documents": self.failed_downloads[:10],  # Include first 10 failures
        }

        # Check if we met minimum threshold
        if len(all_docs) < MIN_EXPECTED_DOCS:
            report["warning"] = (
                f"SIMON: Försäkringskassan verkar ha problem - endast {len(all_docs)} dokument hittades (förväntat: minst {MIN_EXPECTED_DOCS})"
            )
            logger.warning(report["warning"])

        # Write report to file
        report_path = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/forsakringskassan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {report_path}")
        logger.info(f"Scrape complete: {successful}/{len(all_docs)} documents indexed")

        return report


def main():
    """Main entry point"""
    try:
        scraper = ForsakringskassanScraper()
        report = scraper.run()

        # Print summary
        print("\n" + "=" * 60)
        print("FÖRSÄKRINGSKASSAN SCRAPE REPORT")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("=" * 60 + "\n")

        # Exit with error code if below threshold
        if report["total_found"] < MIN_EXPECTED_DOCS:
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
