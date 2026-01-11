#!/usr/bin/env python3
"""
NATURVÅRDSVERKET SCRAPER
Scrapar föreskrifter (NFS), rapporter, vägledningar och allmänna råd
Target: ChromaDB collection 'swedish_gov_docs' med metadata source='naturvardsverket'
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"naturvardsverket_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://www.naturvardsverket.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE = "naturvardsverket"
MIN_DOCS_THRESHOLD = 100

# Target URLs
TARGET_URLS = {
    "foreskrifter": "https://www.naturvardsverket.se/nfs",
    "publikationer": "https://www.naturvardsverket.se/publikationer/",
    "vagledning": "https://www.naturvardsverket.se/vagledning-och-stod/",
}


class NaturvardsverketScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        self.documents = []
        self.seen_urls = set()
        self.pdf_count = 0
        self.html_count = 0

    def generate_doc_id(self, url: str) -> str:
        """Generate unique document ID from URL"""
        return hashlib.md5(url.encode()).hexdigest()

    def fetch_page(self, url: str, retries: int = 3) -> str | None:
        """Fetch page with retry logic"""
        for attempt in range(retries):
            try:
                logger.info(f"Fetching: {url} (attempt {attempt + 1}/{retries})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None

    def extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all PDF links from page"""
        pdfs = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                full_url = urljoin(base_url, href)
                if full_url not in self.seen_urls:
                    self.seen_urls.add(full_url)
                    title = link.get_text(strip=True) or Path(href).stem
                    pdfs.append({"url": full_url, "title": title, "type": "pdf"})
        return pdfs

    def scrape_nfs_foreskrifter(self) -> list[dict]:
        """Scrape NFS föreskrifter"""
        logger.info("=== Scraping NFS Föreskrifter ===")
        documents = []

        # Main NFS index page
        html = self.fetch_page(TARGET_URLS["foreskrifter"])
        if not html:
            return documents

        soup = BeautifulSoup(html, "html.parser")

        # Extract PDF links (NFS documents)
        pdfs = self.extract_pdf_links(soup, TARGET_URLS["foreskrifter"])
        for pdf in pdfs:
            documents.append(
                {
                    "id": self.generate_doc_id(pdf["url"]),
                    "url": pdf["url"],
                    "title": pdf["title"],
                    "content": f"NFS Föreskrift: {pdf['title']}",
                    "metadata": {
                        "source": SOURCE,
                        "doc_type": "foreskrift",
                        "format": "pdf",
                        "scraped_at": datetime.now().isoformat(),
                    },
                }
            )
            self.pdf_count += 1

        # Look for NFS archive/listing pages
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "nfs" in href.lower() and "foreskrift" in href.lower():
                sub_url = urljoin(TARGET_URLS["foreskrifter"], href)
                if sub_url not in self.seen_urls and not sub_url.endswith(".pdf"):
                    self.seen_urls.add(sub_url)
                    sub_html = self.fetch_page(sub_url)
                    if sub_html:
                        sub_soup = BeautifulSoup(sub_html, "html.parser")
                        sub_pdfs = self.extract_pdf_links(sub_soup, sub_url)
                        for pdf in sub_pdfs:
                            documents.append(
                                {
                                    "id": self.generate_doc_id(pdf["url"]),
                                    "url": pdf["url"],
                                    "title": pdf["title"],
                                    "content": f"NFS Föreskrift: {pdf['title']}",
                                    "metadata": {
                                        "source": SOURCE,
                                        "doc_type": "foreskrift",
                                        "format": "pdf",
                                        "scraped_at": datetime.now().isoformat(),
                                    },
                                }
                            )
                            self.pdf_count += 1
                        time.sleep(1)

        logger.info(f"Found {len(documents)} NFS documents")
        return documents

    def scrape_publikationer(self) -> list[dict]:
        """Scrape publikationer (rapporter, broschyrer, böcker)"""
        logger.info("=== Scraping Publikationer ===")
        documents = []

        html = self.fetch_page(TARGET_URLS["publikationer"])
        if not html:
            return documents

        soup = BeautifulSoup(html, "html.parser")

        # Extract all publication links
        pdfs = self.extract_pdf_links(soup, TARGET_URLS["publikationer"])
        for pdf in pdfs:
            documents.append(
                {
                    "id": self.generate_doc_id(pdf["url"]),
                    "url": pdf["url"],
                    "title": pdf["title"],
                    "content": f"Publikation: {pdf['title']}",
                    "metadata": {
                        "source": SOURCE,
                        "doc_type": "publikation",
                        "format": "pdf",
                        "scraped_at": datetime.now().isoformat(),
                    },
                }
            )
            self.pdf_count += 1

        # Look for publication archive/search interface
        # Many Swedish agencies have searchable publication databases
        search_patterns = ["publikation", "rapport", "broschyr", "bok"]
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()
            if any(pattern in text or pattern in href.lower() for pattern in search_patterns):
                sub_url = urljoin(TARGET_URLS["publikationer"], href)
                if sub_url not in self.seen_urls and not sub_url.endswith(".pdf"):
                    self.seen_urls.add(sub_url)
                    sub_html = self.fetch_page(sub_url)
                    if sub_html:
                        sub_soup = BeautifulSoup(sub_html, "html.parser")
                        sub_pdfs = self.extract_pdf_links(sub_soup, sub_url)
                        for pdf in sub_pdfs:
                            documents.append(
                                {
                                    "id": self.generate_doc_id(pdf["url"]),
                                    "url": pdf["url"],
                                    "title": pdf["title"],
                                    "content": f"Publikation: {pdf['title']}",
                                    "metadata": {
                                        "source": SOURCE,
                                        "doc_type": "publikation",
                                        "format": "pdf",
                                        "scraped_at": datetime.now().isoformat(),
                                    },
                                }
                            )
                            self.pdf_count += 1
                        time.sleep(1)

        logger.info(f"Found {len(documents)} publikationer")
        return documents

    def scrape_vagledningar(self) -> list[dict]:
        """Scrape vägledningar och allmänna råd"""
        logger.info("=== Scraping Vägledningar ===")
        documents = []

        html = self.fetch_page(TARGET_URLS["vagledning"])
        if not html:
            return documents

        soup = BeautifulSoup(html, "html.parser")

        # Extract PDFs and HTML guidance pages
        pdfs = self.extract_pdf_links(soup, TARGET_URLS["vagledning"])
        for pdf in pdfs:
            documents.append(
                {
                    "id": self.generate_doc_id(pdf["url"]),
                    "url": pdf["url"],
                    "title": pdf["title"],
                    "content": f"Vägledning: {pdf['title']}",
                    "metadata": {
                        "source": SOURCE,
                        "doc_type": "vagledning",
                        "format": "pdf",
                        "scraped_at": datetime.now().isoformat(),
                    },
                }
            )
            self.pdf_count += 1

        # Extract HTML guidance pages
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()
            if (
                "vagledning" in text
                or "vagledning" in href.lower()
                or "allmanna-rad" in href.lower()
            ):
                sub_url = urljoin(TARGET_URLS["vagledning"], href)
                if (
                    sub_url not in self.seen_urls
                    and not sub_url.endswith(".pdf")
                    and "naturvardsverket.se" in sub_url
                ):
                    self.seen_urls.add(sub_url)
                    sub_html = self.fetch_page(sub_url)
                    if sub_html:
                        sub_soup = BeautifulSoup(sub_html, "html.parser")

                        # Extract main content
                        content_div = (
                            sub_soup.find("main")
                            or sub_soup.find("article")
                            or sub_soup.find("div", class_="content")
                        )
                        if content_div:
                            content_text = content_div.get_text(strip=True, separator=" ")[
                                :5000
                            ]  # Limit content
                            page_title = sub_soup.find("h1")
                            title = (
                                page_title.get_text(strip=True)
                                if page_title
                                else link.get_text(strip=True)
                            )

                            documents.append(
                                {
                                    "id": self.generate_doc_id(sub_url),
                                    "url": sub_url,
                                    "title": title,
                                    "content": content_text,
                                    "metadata": {
                                        "source": SOURCE,
                                        "doc_type": "vagledning",
                                        "format": "html",
                                        "scraped_at": datetime.now().isoformat(),
                                    },
                                }
                            )
                            self.html_count += 1

                        # Also extract any PDFs from guidance pages
                        sub_pdfs = self.extract_pdf_links(sub_soup, sub_url)
                        for pdf in sub_pdfs:
                            documents.append(
                                {
                                    "id": self.generate_doc_id(pdf["url"]),
                                    "url": pdf["url"],
                                    "title": pdf["title"],
                                    "content": f"Vägledning (PDF): {pdf['title']}",
                                    "metadata": {
                                        "source": SOURCE,
                                        "doc_type": "vagledning",
                                        "format": "pdf",
                                        "scraped_at": datetime.now().isoformat(),
                                    },
                                }
                            )
                            self.pdf_count += 1

                        time.sleep(1)

        logger.info(f"Found {len(documents)} vägledningar")
        return documents

    def scrape_all(self) -> list[dict]:
        """Execute full scrape"""
        logger.info("=== STARTING NATURVÅRDSVERKET SCRAPE ===")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")

        # Scrape all sections
        self.documents.extend(self.scrape_nfs_foreskrifter())
        time.sleep(2)

        self.documents.extend(self.scrape_publikationer())
        time.sleep(2)

        self.documents.extend(self.scrape_vagledningar())

        logger.info("=== SCRAPE COMPLETE ===")
        logger.info(f"Total documents: {len(self.documents)}")
        logger.info(f"PDFs: {self.pdf_count}")
        logger.info(f"HTML pages: {self.html_count}")

        return self.documents

    def save_to_chromadb(self, documents: list[dict]) -> dict:
        """Save documents to ChromaDB"""
        if not documents:
            logger.warning("No documents to save to ChromaDB")
            return {"status": "error", "message": "No documents"}

        try:
            logger.info(f"Connecting to ChromaDB at {CHROMADB_PATH}")
            client = chromadb.PersistentClient(path=CHROMADB_PATH)

            # Get or create collection
            collection = client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )

            # Prepare data for ChromaDB
            ids = []
            metadatas = []
            documents_text = []

            for doc in documents:
                ids.append(doc["id"])
                metadatas.append(
                    {"source": SOURCE, "url": doc["url"], "title": doc["title"], **doc["metadata"]}
                )
                documents_text.append(doc["content"])

            # Batch insert
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i : i + batch_size]
                batch_metas = metadatas[i : i + batch_size]
                batch_docs = documents_text[i : i + batch_size]

                collection.upsert(ids=batch_ids, metadatas=batch_metas, documents=batch_docs)
                logger.info(f"Inserted batch {i // batch_size + 1}: {len(batch_ids)} documents")

            logger.info(f"Successfully saved {len(documents)} documents to ChromaDB")
            return {
                "status": "success",
                "collection": COLLECTION_NAME,
                "documents_added": len(documents),
            }

        except Exception as e:
            logger.error(f"ChromaDB error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def generate_report(self) -> dict:
        """Generate final report"""
        total_docs = len(self.documents)

        report = {
            "source": SOURCE,
            "timestamp": datetime.now().isoformat(),
            "total_documents": total_docs,
            "pdf_documents": self.pdf_count,
            "html_documents": self.html_count,
            "threshold": MIN_DOCS_THRESHOLD,
            "threshold_met": total_docs >= MIN_DOCS_THRESHOLD,
            "flag": total_docs < MIN_DOCS_THRESHOLD,
            "categories": {
                "foreskrifter": sum(
                    1 for d in self.documents if d["metadata"]["doc_type"] == "foreskrift"
                ),
                "publikationer": sum(
                    1 for d in self.documents if d["metadata"]["doc_type"] == "publikation"
                ),
                "vagledningar": sum(
                    1 for d in self.documents if d["metadata"]["doc_type"] == "vagledning"
                ),
            },
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
        }

        if report["flag"]:
            report["warning"] = (
                f"FLAGGED: Only {total_docs} documents found (threshold: {MIN_DOCS_THRESHOLD})"
            )
            logger.warning(report["warning"])

        return report


def main():
    scraper = NaturvardsverketScraper()

    # Execute scrape
    documents = scraper.scrape_all()

    # Save documents to JSON first (avoid ChromaDB crash)
    docs_file = f"naturvardsverket_docs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(docs_file, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)
    logger.info(f"Documents saved to {docs_file}")

    # Generate report (without ChromaDB for now)
    report = scraper.generate_report()
    report["documents_file"] = docs_file
    report["chromadb_note"] = "Run index_to_chromadb.py separately to avoid segfault"

    # Save report
    report_file = f"naturvardsverket_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"Report saved to {report_file}")
    logger.info(json.dumps(report, indent=2, ensure_ascii=False))

    return report


if __name__ == "__main__":
    main()
