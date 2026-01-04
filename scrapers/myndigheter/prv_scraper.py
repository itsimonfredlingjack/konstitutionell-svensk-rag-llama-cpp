#!/usr/bin/env python3
"""
PRV (Patent- och registreringsverket) Scraper
Samlar föreskrifter, vägledningar och rapporter från prv.se
"""

import hashlib
import json
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "prv"
BASE_URL = "https://www.prv.se"

# PRV huvudsektioner för dokument
SCRAPE_TARGETS = [
    "/sv/om-prv/lagar-och-regler/foreskrifter/",
    "/sv/om-prv/publikationer/",
    "/sv/stod-och-vagledning/patent/",
    "/sv/stod-och-vagledning/varumarken/",
    "/sv/stod-och-vagledning/design/",
    "/sv/om-prv/statistik-och-rapporter/",
]


class PRVScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Constitutional-AI Scraper (simon@government-research.se)"}
        )
        self.documents = []
        self.seen_urls = set()

    def generate_doc_id(self, url: str) -> str:
        """Generate unique document ID from URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse page"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"  ❌ Error fetching {url}: {e}")
            return None

    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text from page"""
        # Remove script, style, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Find main content
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

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict[str, Any]:
        """Extract metadata from page"""
        metadata = {
            "url": url,
            "source": SOURCE_NAME,
            "scraped_at": datetime.now().isoformat(),
        }

        # Title
        title_tag = soup.find("h1") or soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            metadata["description"] = meta_desc["content"]

        # Published date
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            metadata["published_date"] = time_tag["datetime"]

        # Document type detection
        url_lower = url.lower()
        if "foreskrift" in url_lower:
            metadata["doc_type"] = "föreskrift"
        elif "vagledning" in url_lower or "stod-och-vagledning" in url_lower:
            metadata["doc_type"] = "vägledning"
        elif "statistik" in url_lower or "rapport" in url_lower:
            metadata["doc_type"] = "rapport"
        elif "publikation" in url_lower:
            metadata["doc_type"] = "publikation"
        else:
            metadata["doc_type"] = "information"

        return metadata

    def find_document_links(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        """Find PDF and document links"""
        links = []

        # PDF links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.endswith(".pdf"):
                full_url = urljoin(base_url, href)
                links.append(full_url)

        # Document pages (e.g., /sv/om-prv/lagar-och-regler/foreskrifter/prv-xyz/)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)

            # Check if it's a PRV document page
            if (
                BASE_URL in full_url
                and any(
                    keyword in full_url.lower()
                    for keyword in ["foreskrift", "vagledning", "rapport", "publikation"]
                )
                and full_url not in self.seen_urls
            ):
                links.append(full_url)

        return links

    def scrape_pdf_metadata(self, url: str) -> dict[str, Any]:
        """Create document entry for PDF"""
        filename = url.split("/")[-1]
        return {
            "id": self.generate_doc_id(url),
            "url": url,
            "source": SOURCE_NAME,
            "doc_type": "pdf",
            "title": filename,
            "content": f"PDF-dokument från PRV: {filename}",
            "scraped_at": datetime.now().isoformat(),
        }

    def scrape_page(self, url: str) -> dict[str, Any]:
        """Scrape single page"""
        print(f"  📄 Scraping: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return None

        text = self.extract_text(soup)
        if len(text) < 100:  # Skip pages with minimal content
            return None

        metadata = self.extract_metadata(soup, url)

        doc = {"id": self.generate_doc_id(url), "content": text, **metadata}

        # Find additional documents
        doc_links = self.find_document_links(soup, url)
        for link in doc_links:
            if link not in self.seen_urls:
                self.seen_urls.add(link)
                if link.endswith(".pdf"):
                    self.documents.append(self.scrape_pdf_metadata(link))
                else:
                    # Recursively scrape document pages (max depth 1)
                    sub_doc = self.scrape_page(link)
                    if sub_doc:
                        self.documents.append(sub_doc)
                time.sleep(1)  # Rate limiting

        return doc

    def run(self) -> list[dict[str, Any]]:
        """Run scraper on all targets"""
        print("\n🔍 Starting PRV scraper...")
        print(f"Targets: {len(SCRAPE_TARGETS)} sections\n")

        for target in SCRAPE_TARGETS:
            url = urljoin(BASE_URL, target)
            if url in self.seen_urls:
                continue

            self.seen_urls.add(url)
            print(f"\n📂 Section: {target}")

            doc = self.scrape_page(url)
            if doc:
                self.documents.append(doc)

            time.sleep(2)  # Rate limiting between sections

        print(f"\n✅ Scraping complete: {len(self.documents)} documents")
        return self.documents


def save_to_chromadb(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Save documents to ChromaDB"""
    print("\n💾 Saving to ChromaDB...")

    try:
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        collection = client.get_or_create_collection(COLLECTION_NAME)

        # Prepare data
        ids = [doc["id"] for doc in documents]
        contents = [doc["content"] for doc in documents]
        metadatas = [
            {k: v for k, v in doc.items() if k not in ["id", "content"]} for doc in documents
        ]

        # Upsert (overwrites existing docs with same ID)
        collection.upsert(ids=ids, documents=contents, metadatas=metadatas)

        total_count = collection.count()

        print(f"✅ Saved {len(documents)} documents")
        print(f"📊 Total in collection: {total_count} documents")

        return {
            "saved": len(documents),
            "total_in_collection": total_count,
            "collection": COLLECTION_NAME,
            "source": SOURCE_NAME,
        }

    except Exception as e:
        print(f"❌ ChromaDB error: {e}")
        return {"error": str(e)}


def main():
    """Main execution"""
    start_time = time.time()

    # Run scraper
    scraper = PRVScraper()
    documents = scraper.run()

    if len(documents) == 0:
        print("\n⚠️  No documents found!")
        result = {"status": "warning", "documents_scraped": 0, "message": "No documents found"}
    else:
        # Save to ChromaDB
        db_result = save_to_chromadb(documents)

        # Build result
        result = {
            "status": "success",
            "source": SOURCE_NAME,
            "documents_scraped": len(documents),
            "chromadb": db_result,
            "execution_time_seconds": round(time.time() - start_time, 2),
            "timestamp": datetime.now().isoformat(),
        }

        # Flag if low count
        if len(documents) < 100:
            result["flag"] = f"⚠️  Only {len(documents)} documents - may need deeper scraping"

    # Save JSON report
    report_path = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/prv_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Report saved: {report_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return result


if __name__ == "__main__":
    main()
