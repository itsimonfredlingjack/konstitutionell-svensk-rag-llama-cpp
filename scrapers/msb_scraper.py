#!/usr/bin/env python3
"""
MSB (Myndigheten för samhällsskydd och beredskap) Document Scraper
Scrapes reports, guidelines, regulations, and educational material from msb.se
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings

# Configuration
BASE_URL = "https://www.msb.se"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_ID = "msb"
MIN_DOCUMENTS = 100

# Headers to mimic browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# Key sections to scrape
SCRAPE_SECTIONS = [
    "/sv/publikationer",
    "/sv/amnesomraden/informationssakerhet-cybersakerhet-och-sakra-kommunikationer",
    "/sv/amnesomraden/krisberedskap-och-civilt-forsvar",
    "/sv/amnesomraden/skydd-mot-olyckor-och-farliga-amnen",
    "/sv/regler",
    "/sv/utbildning-och-ovning",
]


class MSBScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.visited_urls: set[str] = set()
        self.documents: list[dict] = []
        self.errors: list[dict] = []

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
        )

        try:
            self.collection = self.chroma_client.get_collection(name=COLLECTION_NAME)
            print(f"[INFO] Connected to existing collection: {COLLECTION_NAME}")
        except:
            self.collection = self.chroma_client.create_collection(
                name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
            )
            print(f"[INFO] Created new collection: {COLLECTION_NAME}")

    def fetch_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a page with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except requests.RequestException as e:
                if attempt == retries - 1:
                    self.errors.append(
                        {"url": url, "error": str(e), "timestamp": datetime.now().isoformat()}
                    )
                    print(f"[ERROR] Failed to fetch {url}: {e}")
                    return None
                time.sleep(2**attempt)  # Exponential backoff
        return None

    def extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all PDF links from a page"""
        pdf_links = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Check if it's a PDF
            if not (href.lower().endswith(".pdf") or "/pdf/" in href.lower()):
                continue

            full_url = urljoin(base_url, href)

            # Extract metadata
            title = link.get_text(strip=True)

            # Try to find associated metadata
            parent = link.find_parent(["div", "article", "section"])
            description = ""
            date = None

            if parent:
                # Look for description
                desc_elem = parent.find(
                    ["p", "div"], class_=re.compile(r"(description|summary|ingress)", re.I)
                )
                if desc_elem:
                    description = desc_elem.get_text(strip=True)

                # Look for date
                date_elem = parent.find(
                    ["time", "span"], class_=re.compile(r"(date|published)", re.I)
                )
                if date_elem:
                    date = date_elem.get_text(strip=True)
                elif parent.find("time"):
                    date = parent.find("time").get("datetime") or parent.find("time").get_text(
                        strip=True
                    )

            pdf_links.append(
                {
                    "url": full_url,
                    "title": title or os.path.basename(urlparse(full_url).path),
                    "description": description,
                    "date": date,
                    "source_page": base_url,
                }
            )

        return pdf_links

    def extract_document_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract structured document metadata from a page"""
        metadata = {
            "url": url,
            "title": "",
            "description": "",
            "content": "",
            "document_type": "webpage",
            "date": None,
            "categories": [],
        }

        # Title
        title_elem = soup.find("h1") or soup.find("title")
        if title_elem:
            metadata["title"] = title_elem.get_text(strip=True)

        # Description/Summary
        for selector in ['meta[name="description"]', 'meta[property="og:description"]']:
            meta = soup.select_one(selector)
            if meta:
                metadata["description"] = meta.get("content", "")
                break

        # Main content
        content_elem = soup.find(["article", "main"]) or soup.find(
            "div", class_=re.compile(r"(content|main)", re.I)
        )
        if content_elem:
            # Remove navigation, headers, footers
            for unwanted in content_elem.find_all(["nav", "header", "footer", "aside"]):
                unwanted.decompose()
            metadata["content"] = content_elem.get_text(separator="\n", strip=True)
        else:
            metadata["content"] = soup.get_text(separator="\n", strip=True)[:5000]  # Fallback

        # Date
        date_elem = soup.find("time") or soup.find(class_=re.compile(r"(date|published)", re.I))
        if date_elem:
            metadata["date"] = date_elem.get("datetime") or date_elem.get_text(strip=True)

        # Categories from breadcrumbs
        breadcrumbs = soup.find(["nav", "ol"], class_=re.compile(r"breadcrumb", re.I))
        if breadcrumbs:
            metadata["categories"] = [a.get_text(strip=True) for a in breadcrumbs.find_all("a")]

        # Document type detection
        title_lower = metadata["title"].lower()
        if any(keyword in title_lower for keyword in ["rapport", "report"]):
            metadata["document_type"] = "rapport"
        elif any(keyword in title_lower for keyword in ["vägledning", "guide", "handbok"]):
            metadata["document_type"] = "vägledning"
        elif any(keyword in title_lower for keyword in ["föreskrift", "regel", "förordning"]):
            metadata["document_type"] = "föreskrift"
        elif any(keyword in title_lower for keyword in ["utbildning", "kurs", "webinar"]):
            metadata["document_type"] = "utbildning"

        return metadata

    def crawl_section(self, url: str, depth: int = 0, max_depth: int = 3):
        """Recursively crawl a section"""
        if depth > max_depth or url in self.visited_urls:
            return

        self.visited_urls.add(url)
        print(f"[CRAWL] Depth {depth}: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return

        # Extract PDFs
        pdf_links = self.extract_pdf_links(soup, url)
        for pdf in pdf_links:
            if pdf["url"] not in [d["url"] for d in self.documents]:
                self.documents.append({**pdf, "document_type": "pdf", "source": SOURCE_ID})
                print(f"[PDF] Found: {pdf['title'][:60]}...")

        # Extract page content
        if any(
            indicator in url
            for indicator in ["/publikation/", "/vagledning/", "/foreskrift/", "/utbildning/"]
        ):
            metadata = self.extract_document_metadata(soup, url)
            if metadata["title"] and len(metadata["content"]) > 200:
                metadata["source"] = SOURCE_ID
                self.documents.append(metadata)
                print(f"[PAGE] Extracted: {metadata['title'][:60]}...")

        # Find links to crawl deeper
        if depth < max_depth:
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(url, href)

                # Only follow MSB links
                if not full_url.startswith(BASE_URL):
                    continue

                # Skip non-content URLs
                if any(
                    skip in full_url for skip in ["#", "javascript:", "mailto:", "/sok", "/search"]
                ):
                    continue

                # Follow relevant links
                if any(
                    keyword in full_url.lower()
                    for keyword in [
                        "publikation",
                        "rapport",
                        "vagledning",
                        "foreskrift",
                        "utbildning",
                        "dokument",
                        "material",
                        "regel",
                    ]
                ):
                    time.sleep(0.5)  # Rate limiting
                    self.crawl_section(full_url, depth + 1, max_depth)

    def store_in_chromadb(self):
        """Store all documents in ChromaDB"""
        print(f"\n[STORAGE] Storing {len(self.documents)} documents in ChromaDB...")

        for i, doc in enumerate(self.documents):
            try:
                # Create unique ID
                doc_id = hashlib.md5(doc["url"].encode()).hexdigest()

                # Prepare content for embedding
                content = (
                    f"{doc.get('title', '')} {doc.get('description', '')} {doc.get('content', '')}"[
                        :8000
                    ]
                )

                # Prepare metadata
                metadata = {
                    "source": SOURCE_ID,
                    "url": doc["url"],
                    "title": doc.get("title", "")[:500],
                    "document_type": doc.get("document_type", "unknown"),
                    "date": doc.get("date", ""),
                    "scraped_at": datetime.now().isoformat(),
                }

                # Add to collection
                self.collection.upsert(ids=[doc_id], documents=[content], metadatas=[metadata])

                if (i + 1) % 10 == 0:
                    print(f"[STORAGE] Stored {i + 1}/{len(self.documents)} documents...")

            except Exception as e:
                self.errors.append(
                    {
                        "document": doc.get("url", "unknown"),
                        "error": f"ChromaDB storage error: {e!s}",
                        "timestamp": datetime.now().isoformat(),
                    }
                )
                print(f"[ERROR] Failed to store {doc.get('url', 'unknown')}: {e}")

        print(f"[STORAGE] Completed! Stored {len(self.documents)} documents.")

    def generate_report(self) -> dict:
        """Generate final JSON report"""
        report = {
            "source": SOURCE_ID,
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_documents": len(self.documents),
                "total_urls_visited": len(self.visited_urls),
                "total_errors": len(self.errors),
                "document_types": {},
            },
            "documents": self.documents,
            "errors": self.errors,
            "flag": len(self.documents) < MIN_DOCUMENTS,
            "flag_reason": f"Found only {len(self.documents)} documents (minimum: {MIN_DOCUMENTS})"
            if len(self.documents) < MIN_DOCUMENTS
            else None,
        }

        # Count document types
        for doc in self.documents:
            doc_type = doc.get("document_type", "unknown")
            report["statistics"]["document_types"][doc_type] = (
                report["statistics"]["document_types"].get(doc_type, 0) + 1
            )

        return report

    def run(self):
        """Execute the full scraping process"""
        print(f"\n{'='*60}")
        print("MSB DOCUMENT SCRAPER")
        print(f"{'='*60}\n")

        start_time = time.time()

        # Crawl main sections
        for section in SCRAPE_SECTIONS:
            url = urljoin(BASE_URL, section)
            print(f"\n[SECTION] Starting: {section}")
            self.crawl_section(url, depth=0, max_depth=2)

        # Store in ChromaDB
        self.store_in_chromadb()

        # Generate report
        report = self.generate_report()

        # Save report
        report_path = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/reports/msb_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time

        # Print summary
        print(f"\n{'='*60}")
        print("SCRAPING COMPLETE")
        print(f"{'='*60}")
        print(f"Time elapsed: {elapsed:.1f}s")
        print(f"Documents found: {report['statistics']['total_documents']}")
        print(f"URLs visited: {report['statistics']['total_urls_visited']}")
        print(f"Errors: {report['statistics']['total_errors']}")
        print("\nDocument types:")
        for doc_type, count in report["statistics"]["document_types"].items():
            print(f"  - {doc_type}: {count}")

        if report["flag"]:
            print(f"\n⚠️  WARNING: {report['flag_reason']}")

        print(f"\nReport saved: {report_path}")
        print(f"{'='*60}\n")

        return report


if __name__ == "__main__":
    scraper = MSBScraper()
    report = scraper.run()
