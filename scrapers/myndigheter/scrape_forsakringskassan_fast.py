#!/usr/bin/env python3
"""
Försäkringskassan Document Scraper - FAST MODE
Scrapes document metadata without downloading PDFs (for quick indexing)

Usage:
    python scrape_forsakringskassan_fast.py
"""

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "https://www.forsakringskassan.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
MIN_EXPECTED_DOCS = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


class ForsakringskassanFastScraper:
    """Fast scraper - metadata only"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.processed_urls: set[str] = set()

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
        )
        logger.info(f"ChromaDB ready at {CHROMADB_PATH}")

    def fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse webpage"""
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def scrape_publications_page(self) -> list[dict]:
        """Scrape main publications page"""
        url = f"{BASE_URL}/om-forsakringskassan/publikationer"
        logger.info(f"Scraping: {url}")

        soup = self.fetch_page(url)
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if not (".pdf" in href or "/download/" in href):
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in self.processed_urls:
                continue

            self.processed_urls.add(full_url)

            title = link.get_text(strip=True)

            # Extract context
            doc_type = "publikation"
            year = None

            parent = link.find_parent(["li", "div", "section"])
            if parent:
                parent_text = parent.get_text().lower()

                if "rapport" in parent_text:
                    doc_type = "rapport"
                elif "vägledning" in parent_text:
                    doc_type = "vägledning"
                elif "ställningstagande" in parent_text:
                    doc_type = "ställningstagande"
                elif "regeringsuppdrag" in parent_text:
                    doc_type = "regeringsuppdrag"
                elif "statistik" in parent_text or "siffror" in parent_text:
                    doc_type = "statistik"

                import re

                year_match = re.search(r"(19|20)\d{2}", parent.get_text())
                if year_match:
                    year = year_match.group(0)

            documents.append(
                {
                    "url": full_url,
                    "title": title or os.path.basename(urlparse(full_url).path),
                    "type": doc_type,
                    "year": year,
                }
            )

        logger.info(f"Found {len(documents)} documents")
        return documents

    def scrape_statistics_page(self) -> list[dict]:
        """Scrape statistics page"""
        url = f"{BASE_URL}/statistik-och-analys"
        logger.info(f"Scraping: {url}")

        soup = self.fetch_page(url)
        documents = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if not (".pdf" in href or "/download/" in href):
                continue

            full_url = urljoin(BASE_URL, href)
            if full_url in self.processed_urls:
                continue

            self.processed_urls.add(full_url)

            documents.append(
                {
                    "url": full_url,
                    "title": link.get_text(strip=True),
                    "type": "statistik",
                    "year": None,
                }
            )

        logger.info(f"Found {len(documents)} documents")
        return documents

    def index_documents(self, documents: list[dict]) -> int:
        """Index documents to ChromaDB (metadata only)"""
        successful = 0

        for doc in documents:
            try:
                doc_id = hashlib.sha256(doc["url"].encode()).hexdigest()

                # Create searchable text from metadata
                text = f"""
Dokument: {doc['title']}
Typ: {doc['type']}
År: {doc.get('year', 'okänt')}
Källa: Försäkringskassan
URL: {doc['url']}

Detta är ett dokument från Försäkringskassan. För fullständig text, ladda ner PDF från URL:en ovan.
                """.strip()

                metadata = {
                    "source": "forsakringskassan",
                    "url": doc["url"],
                    "title": doc["title"],
                    "type": doc["type"],
                    "scraped_at": datetime.now().isoformat(),
                }

                if doc.get("year"):
                    metadata["year"] = doc["year"]

                self.collection.upsert(ids=[doc_id], documents=[text], metadatas=[metadata])

                successful += 1

            except Exception as e:
                logger.error(f"Failed to index {doc['title']}: {e}")

        logger.info(f"Indexed {successful}/{len(documents)} documents")
        return successful

    def run(self) -> dict:
        """Execute scrape"""
        start_time = time.time()
        logger.info("Starting FAST scrape of Försäkringskassan")

        all_docs = []
        all_docs.extend(self.scrape_publications_page())
        time.sleep(1)
        all_docs.extend(self.scrape_statistics_page())

        logger.info(f"Total documents found: {len(all_docs)}")

        # Index all at once
        successful = self.index_documents(all_docs)

        elapsed = time.time() - start_time

        report = {
            "source": "forsakringskassan",
            "mode": "FAST (metadata only, no PDF extraction)",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(elapsed, 2),
            "total_found": len(all_docs),
            "successful": successful,
            "failed": len(all_docs) - successful,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
        }

        if len(all_docs) < MIN_EXPECTED_DOCS:
            report["warning"] = (
                f"SIMON: Försäkringskassan verkar ha problem - endast {len(all_docs)} dokument hittades"
            )
            logger.warning(report["warning"])

        # Write report
        report_path = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/forsakringskassan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report: {report_path}")
        return report


def main():
    try:
        scraper = ForsakringskassanFastScraper()
        report = scraper.run()

        print("\n" + "=" * 60)
        print("FÖRSÄKRINGSKASSAN SCRAPE COMPLETE")
        print("=" * 60)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("=" * 60)

        sys.exit(0 if report["total_found"] >= MIN_EXPECTED_DOCS else 1)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
