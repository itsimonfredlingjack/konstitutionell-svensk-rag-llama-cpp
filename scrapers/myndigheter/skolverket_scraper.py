#!/usr/bin/env python3
"""
SKOLVERKET SCRAPER
==================
Scrapes documents from skolverket.se and stores in ChromaDB.

TARGET AREAS:
- Läroplaner (curricula)
- Föreskrifter (SKOLFS - regulations)
- Statistik (statistics)
- Allmänna råd (general advice)
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import aiohttp
import chromadb
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "skolverket"
MIN_DOC_THRESHOLD = 100

# Skolverket target URLs (verified 2025-12-07)
SKOLVERKET_URLS = {
    "laroplaner": "https://www.skolverket.se/undervisning/grundskolan/laroplan-och-kursplaner-for-grundskolan",
    "gymnasielaroplaner": "https://www.skolverket.se/undervisning/gymnasieskolan/laroplan-program-och-amnen-i-gymnasieskolan",
    "foreskrifter": "https://www.skolverket.se/regler-och-ansvar/sok-forordningar-och-foreskrifter-skolfs",
    "statistik": "https://www.skolverket.se/skolutveckling/statistik",
    "allmanna_rad": "https://www.skolverket.se/styrning-och-ansvar/regler-och-ansvar/allmanna-rad",
    "publikationer": "https://www.skolverket.se/sok-publikationer",
}


class SkolverketScraper:
    """Async scraper for Skolverket documents"""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
        except:
            self.collection = self.client.create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )

        self.session: aiohttp.ClientSession | None = None
        self.stats = {
            "total_found": 0,
            "new_added": 0,
            "duplicates": 0,
            "errors": 0,
            "by_category": {},
        }

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "Mozilla/5.0 (compatible; SkolverketScraper/1.0)"},
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_doc_id(self, url: str, title: str) -> str:
        """Generate unique document ID"""
        content = f"{url}|{title}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _exists_in_db(self, doc_id: str) -> bool:
        """Check if document already exists"""
        try:
            result = self.collection.get(ids=[doc_id])
            return len(result["ids"]) > 0
        except:
            return False

    async def fetch_page(self, url: str) -> str | None:
        """Fetch page HTML with error handling"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            self.stats["errors"] += 1
            return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def extract_pdf_links(self, html: str, base_url: str) -> list[dict[str, str]]:
        """Extract PDF links from HTML"""
        soup = BeautifulSoup(html, "lxml")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf"):
                full_url = urljoin(base_url, href)
                title = a.get_text(strip=True) or "Untitled Document"
                links.append({"url": full_url, "title": title, "type": "pdf"})

        return links

    async def extract_page_content(self, html: str) -> str:
        """Extract main text content from HTML page"""
        soup = BeautifulSoup(html, "lxml")

        # Remove scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Find main content area (common Skolverket selectors)
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile("content|main|article", re.I))
            or soup.find("body")
        )

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
            # Clean up excessive whitespace
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()

        return ""

    async def scrape_laroplaner(self, url: str) -> list[dict]:
        """Scrape curriculum documents"""
        logger.info(f"Scraping Läroplaner from {url}")
        html = await self.fetch_page(url)
        if not html:
            return []

        documents = []

        # Extract PDFs
        pdf_links = await self.extract_pdf_links(html, url)
        for link in pdf_links:
            doc_id = self._generate_doc_id(link["url"], link["title"])
            if not self._exists_in_db(doc_id):
                documents.append(
                    {
                        "id": doc_id,
                        "url": link["url"],
                        "title": link["title"],
                        "category": "laroplan",
                        "type": "pdf",
                    }
                )

        # Also scrape the page content itself
        page_content = await self.extract_page_content(html)
        if page_content and len(page_content) > 200:
            doc_id = self._generate_doc_id(url, "Läroplaner - Huvudsida")
            if not self._exists_in_db(doc_id):
                documents.append(
                    {
                        "id": doc_id,
                        "url": url,
                        "title": "Läroplaner - Huvudsida",
                        "content": page_content,
                        "category": "laroplan",
                        "type": "webpage",
                    }
                )

        return documents

    async def scrape_foreskrifter(self, url: str) -> list[dict]:
        """Scrape SKOLFS regulations"""
        logger.info(f"Scraping Föreskrifter from {url}")
        documents = []

        # The main SKOLFS search page
        html = await self.fetch_page(url)
        if html:
            soup = BeautifulSoup(html, "lxml")

            # Look for SKOLFS documents (common pattern: SKOLFS 2023:123)
            skolfs_pattern = re.compile(r"SKOLFS\s+\d{4}:\d+", re.I)

            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                href = a["href"]

                # Match SKOLFS pattern or PDF links from skolfs.skolverket.se
                if (
                    skolfs_pattern.search(text)
                    or "SKOLFS" in text.upper()
                    or "skolfs.skolverket.se" in href
                    or (href.endswith(".pdf") and "SKOLFS" in href.upper())
                ):
                    full_url = urljoin(url, href)
                    doc_id = self._generate_doc_id(full_url, text)

                    if not self._exists_in_db(doc_id):
                        documents.append(
                            {
                                "id": doc_id,
                                "url": full_url,
                                "title": text or "SKOLFS Dokument",
                                "category": "foreskrift",
                                "type": "pdf" if full_url.endswith(".pdf") else "webpage",
                            }
                        )

        return documents

    async def scrape_statistik(self, url: str) -> list[dict]:
        """Scrape statistics documents"""
        logger.info(f"Scraping Statistik from {url}")
        html = await self.fetch_page(url)
        if not html:
            return []

        documents = []
        soup = BeautifulSoup(html, "lxml")

        # Find statistical reports and Excel files
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith((".pdf", ".xlsx", ".xls")):
                full_url = urljoin(url, href)
                title = a.get_text(strip=True) or "Statistikdokument"
                doc_id = self._generate_doc_id(full_url, title)

                if not self._exists_in_db(doc_id):
                    documents.append(
                        {
                            "id": doc_id,
                            "url": full_url,
                            "title": title,
                            "category": "statistik",
                            "type": Path(href).suffix[1:],  # pdf, xlsx, etc.
                        }
                    )

        return documents

    async def scrape_allmanna_rad(self, url: str) -> list[dict]:
        """Scrape general advice documents"""
        logger.info(f"Scraping Allmänna råd from {url}")
        html = await self.fetch_page(url)
        if not html:
            return []

        documents = []

        # Extract PDFs
        pdf_links = await self.extract_pdf_links(html, url)
        for link in pdf_links:
            doc_id = self._generate_doc_id(link["url"], link["title"])
            if not self._exists_in_db(doc_id):
                documents.append(
                    {
                        "id": doc_id,
                        "url": link["url"],
                        "title": link["title"],
                        "category": "allmanna_rad",
                        "type": "pdf",
                    }
                )

        # Extract page content
        page_content = await self.extract_page_content(html)
        if page_content and len(page_content) > 200:
            doc_id = self._generate_doc_id(url, "Allmänna råd - Huvudsida")
            if not self._exists_in_db(doc_id):
                documents.append(
                    {
                        "id": doc_id,
                        "url": url,
                        "title": "Allmänna råd - Huvudsida",
                        "content": page_content,
                        "category": "allmanna_rad",
                        "type": "webpage",
                    }
                )

        return documents

    async def fetch_document_content(self, doc: dict) -> str | None:
        """Fetch actual document content (for PDFs and webpages)"""
        if doc.get("content"):
            return doc["content"]

        if doc["type"] == "pdf":
            # For PDFs, just store URL - actual text extraction would need pdfplumber
            return f"PDF Document: {doc['title']}\nURL: {doc['url']}"

        elif doc["type"] == "webpage":
            html = await self.fetch_page(doc["url"])
            if html:
                return await self.extract_page_content(html)

        return None

    def store_documents(self, documents: list[dict]):
        """Batch store documents in ChromaDB"""
        if not documents:
            return

        ids = []
        texts = []
        metadatas = []

        for doc in documents:
            ids.append(doc["id"])
            # Use content if available, otherwise placeholder
            content = doc.get("content", f"Document: {doc['title']}\nURL: {doc['url']}")
            texts.append(content)
            metadatas.append(
                {
                    "source": SOURCE_NAME,
                    "url": doc["url"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "type": doc["type"],
                    "scraped_at": datetime.now().isoformat(),
                }
            )

        try:
            self.collection.add(ids=ids, documents=texts, metadatas=metadatas)
            self.stats["new_added"] += len(documents)
            logger.info(f"Stored {len(documents)} documents")
        except Exception as e:
            logger.error(f"Error storing documents: {e}")
            self.stats["errors"] += 1

    async def run(self):
        """Main scraping workflow"""
        logger.info("=" * 60)
        logger.info("SKOLVERKET SCRAPER STARTING")
        logger.info("=" * 60)

        start_time = time.time()

        # Scrape each category
        for category, url in SKOLVERKET_URLS.items():
            logger.info(f"\n--- Scraping {category} ---")

            if category in ["laroplaner", "gymnasielaroplaner"]:
                documents = await self.scrape_laroplaner(url)
            elif category == "foreskrifter":
                documents = await self.scrape_foreskrifter(url)
            elif category == "statistik":
                documents = await self.scrape_statistik(url)
            elif category == "allmanna_rad":
                documents = await self.scrape_allmanna_rad(url)
            elif category == "publikationer":
                # Publikationer uses same method as laroplaner
                documents = await self.scrape_laroplaner(url)
            else:
                documents = []

            self.stats["total_found"] += len(documents)
            self.stats["by_category"][category] = len(documents)

            if documents:
                # Fetch content for non-PDF documents
                for doc in documents:
                    if doc["type"] != "pdf" and "content" not in doc:
                        content = await self.fetch_document_content(doc)
                        if content:
                            doc["content"] = content

                self.store_documents(documents)
                logger.info(f"Category {category}: {len(documents)} documents")

            # Rate limiting
            await asyncio.sleep(2)

        elapsed = time.time() - start_time

        # Final report
        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total documents found: {self.stats['total_found']}")
        logger.info(f"New documents added: {self.stats['new_added']}")
        logger.info(f"Duplicates skipped: {self.stats['duplicates']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Time elapsed: {elapsed:.2f}s")
        logger.info("\nBy category:")
        for cat, count in self.stats["by_category"].items():
            logger.info(f"  {cat}: {count}")

        # Check threshold
        if self.stats["new_added"] < MIN_DOC_THRESHOLD:
            logger.warning(
                f"\n⚠️  WARNING: Only {self.stats['new_added']} documents found (threshold: {MIN_DOC_THRESHOLD})"
            )
        else:
            logger.info(f"\n✓ Success: {self.stats['new_added']} documents collected")

        return self.stats


async def main():
    """Entry point"""
    async with SkolverketScraper() as scraper:
        stats = await scraper.run()

        # Write JSON report
        report_path = Path(__file__).parent / "skolverket_report.json"
        report = {
            "timestamp": datetime.now().isoformat(),
            "source": SOURCE_NAME,
            "stats": stats,
            "chromadb_path": CHROMADB_PATH,
            "collection": COLLECTION_NAME,
            "threshold_met": stats["new_added"] >= MIN_DOC_THRESHOLD,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n📄 Report written to: {report_path}")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
