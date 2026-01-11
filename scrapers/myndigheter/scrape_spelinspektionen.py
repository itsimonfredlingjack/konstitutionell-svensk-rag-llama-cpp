#!/usr/bin/env python3
"""
Spelinspektionen Document Scraper
Targets: Föreskrifter, Beslut, Tillsyn, Publikationer
ChromaDB: swedish_gov_docs | source: spelinspektionen
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SpelinspeketionenScraper:
    """Scraper for Spelinspektionen documents"""

    BASE_URL = "https://spelinspektionen.se"
    SOURCE = "spelinspektionen"

    # Target URLs based on WebFetch analysis
    TARGETS = {
        "föreskrifter": "/lagar-regler/foreskrifter/",
        "beslut": "/vara-beslut/beslutslista/",
        "tillsyn": "/vara-beslut/",
        "publikationer": "/om-oss/rapporter--remissvar/",
        "statistik": "/om-oss/statistik/",
        "allmanna_handlingar": "/om-oss/allmanna-handlingar/",
    }

    def __init__(self, chromadb_path: str = "chromadb_data"):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; SwedishGovScraper/1.0; Constitutional AI Research)"
            }
        )

        # ChromaDB setup
        self.client = chromadb.PersistentClient(path=chromadb_path)
        self.collection = self.client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish Government Documents"}
        )

        self.stats = {"scraped": 0, "added": 0, "skipped": 0, "errors": 0}

    def generate_doc_id(self, url: str, title: str) -> str:
        """Generate unique document ID"""
        content = f"{url}|{title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def fetch_page(self, url: str) -> BeautifulSoup | None:
        """Fetch and parse a page"""
        try:
            full_url = urljoin(self.BASE_URL, url)
            logger.info(f"Fetching: {full_url}")

            response = self.session.get(full_url, timeout=30)
            response.raise_for_status()

            return BeautifulSoup(response.text, "html.parser")

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            self.stats["errors"] += 1
            return None

    def extract_document_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract document links from a page"""
        documents = []

        # Find all links to PDFs, Word docs, or detail pages
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            # Skip empty links
            if not text or not href:
                continue

            # Skip navigation/footer links
            if any(skip in href.lower() for skip in ["#", "javascript:", "mailto:", "tel:"]):
                continue

            full_url = urljoin(base_url, href)

            # Determine document type
            doc_type = "webpage"
            if href.lower().endswith(".pdf"):
                doc_type = "pdf"
            elif href.lower().endswith((".doc", ".docx")):
                doc_type = "word"

            documents.append({"url": full_url, "title": text, "type": doc_type})

        return documents

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content from page"""
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()

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

    def scrape_foreskrifter(self) -> list[dict]:
        """Scrape Föreskrifter (Regulations)"""
        logger.info("=== Scraping Föreskrifter ===")
        documents = []

        soup = self.fetch_page(self.TARGETS["föreskrifter"])
        if not soup:
            return documents

        # Extract all document links
        doc_links = self.extract_document_links(soup, self.BASE_URL + self.TARGETS["föreskrifter"])

        for doc in doc_links:
            if doc["type"] == "pdf":
                # For PDFs, store metadata only
                documents.append(
                    {
                        "url": doc["url"],
                        "title": doc["title"],
                        "content": f"PDF Document: {doc['title']}\nURL: {doc['url']}",
                        "category": "föreskrifter",
                        "doc_type": "pdf",
                    }
                )
            elif doc["type"] == "webpage" and "spelinspektionen.se" in doc["url"]:
                # Fetch webpage content
                detail_soup = self.fetch_page(doc["url"])
                if detail_soup:
                    content = self.extract_text_content(detail_soup)
                    documents.append(
                        {
                            "url": doc["url"],
                            "title": doc["title"],
                            "content": content,
                            "category": "föreskrifter",
                            "doc_type": "webpage",
                        }
                    )
                time.sleep(0.5)  # Rate limiting

        logger.info(f"Found {len(documents)} föreskrifter documents")
        return documents

    def scrape_beslut(self) -> list[dict]:
        """Scrape Beslut (Decisions)"""
        logger.info("=== Scraping Beslut ===")
        documents = []

        soup = self.fetch_page(self.TARGETS["beslut"])
        if not soup:
            return documents

        # Look for decision items (adapt to actual HTML structure)
        decision_items = soup.find_all(
            ["article", "div"],
            class_=lambda c: c
            and any(x in str(c).lower() for x in ["decision", "beslut", "item", "post"]),
        )

        for item in decision_items:
            title_elem = item.find(["h1", "h2", "h3", "h4", "a"])
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            link = item.find("a", href=True)

            if link:
                url = urljoin(self.BASE_URL, link["href"])
                detail_soup = self.fetch_page(url)

                if detail_soup:
                    content = self.extract_text_content(detail_soup)
                    documents.append(
                        {
                            "url": url,
                            "title": title,
                            "content": content,
                            "category": "beslut",
                            "doc_type": "webpage",
                        }
                    )
                    time.sleep(0.5)

        # If no structured items found, extract all links
        if not documents:
            doc_links = self.extract_document_links(soup, self.BASE_URL + self.TARGETS["beslut"])
            for doc in doc_links[:20]:  # Limit to first 20 links
                if "spelinspektionen.se" in doc["url"]:
                    detail_soup = self.fetch_page(doc["url"])
                    if detail_soup:
                        content = self.extract_text_content(detail_soup)
                        documents.append(
                            {
                                "url": doc["url"],
                                "title": doc["title"],
                                "content": content,
                                "category": "beslut",
                                "doc_type": "webpage",
                            }
                        )
                    time.sleep(0.5)

        logger.info(f"Found {len(documents)} beslut documents")
        return documents

    def scrape_publikationer(self) -> list[dict]:
        """Scrape Publikationer (Publications)"""
        logger.info("=== Scraping Publikationer ===")
        documents = []

        # Scrape both reports and statistics
        for category in ["publikationer", "statistik"]:
            soup = self.fetch_page(self.TARGETS[category])
            if not soup:
                continue

            doc_links = self.extract_document_links(soup, self.BASE_URL + self.TARGETS[category])

            for doc in doc_links:
                if doc["type"] == "pdf":
                    documents.append(
                        {
                            "url": doc["url"],
                            "title": doc["title"],
                            "content": f"PDF Document: {doc['title']}\nURL: {doc['url']}",
                            "category": category,
                            "doc_type": "pdf",
                        }
                    )
                elif doc["type"] == "webpage" and "spelinspektionen.se" in doc["url"]:
                    detail_soup = self.fetch_page(doc["url"])
                    if detail_soup:
                        content = self.extract_text_content(detail_soup)
                        documents.append(
                            {
                                "url": doc["url"],
                                "title": doc["title"],
                                "content": content,
                                "category": category,
                                "doc_type": "webpage",
                            }
                        )
                    time.sleep(0.5)

        logger.info(f"Found {len(documents)} publikationer documents")
        return documents

    def store_document(self, doc: dict) -> bool:
        """Store document in ChromaDB"""
        try:
            doc_id = self.generate_doc_id(doc["url"], doc["title"])

            # Check if already exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    logger.debug(f"Skipping existing: {doc['title'][:50]}")
                    self.stats["skipped"] += 1
                    return False
            except:
                pass

            # Store new document
            self.collection.add(
                ids=[doc_id],
                documents=[doc["content"]],
                metadatas=[
                    {
                        "source": self.SOURCE,
                        "url": doc["url"],
                        "title": doc["title"],
                        "category": doc["category"],
                        "doc_type": doc["doc_type"],
                        "scraped_at": datetime.now().isoformat(),
                    }
                ],
            )

            logger.info(f"✓ Added: {doc['title'][:60]}")
            self.stats["added"] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to store document: {e}")
            self.stats["errors"] += 1
            return False

    def run(self) -> dict:
        """Run full scrape operation"""
        start_time = time.time()
        logger.info("=== STARTING SPELINSPEKTIONEN SCRAPE ===")

        all_documents = []

        # Scrape all categories
        all_documents.extend(self.scrape_foreskrifter())
        all_documents.extend(self.scrape_beslut())
        all_documents.extend(self.scrape_publikationer())

        self.stats["scraped"] = len(all_documents)

        # Store all documents
        logger.info(f"\n=== Storing {len(all_documents)} documents in ChromaDB ===")
        for doc in all_documents:
            self.store_document(doc)

        duration = time.time() - start_time

        # Final report
        report = {
            "source": self.SOURCE,
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration, 2),
            "stats": self.stats,
            "collection_total": self.collection.count(),
        }

        logger.info("\n=== SCRAPE COMPLETE ===")
        logger.info(f"Scraped: {self.stats['scraped']}")
        logger.info(f"Added: {self.stats['added']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Duration: {duration:.2f}s")
        logger.info(f"Total in collection: {self.collection.count()}")

        return report


def main():
    scraper = SpelinspeketionenScraper(
        chromadb_path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    )

    report = scraper.run()

    # Save report
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/spelinspektionen_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Report saved: {output_file}")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
