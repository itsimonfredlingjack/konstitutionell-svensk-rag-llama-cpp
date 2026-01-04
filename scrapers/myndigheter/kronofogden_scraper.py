#!/usr/bin/env python3
"""
KRONOFOGDEN SCRAPER
Scrapes documents from Kronofogden (Swedish Enforcement Authority)

Target categories:
- Föreskrifter (KFMFS)
- Allmänna råd (KFM A)
- Meddelanden (KFM M)
- Handböcker
- Rapporter och publikationer
- Årsredovisningar

Storage: ChromaDB collection 'swedish_gov_docs' with source: 'kronofogden'
"""

import asyncio
import hashlib
import json
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import aiohttp
import chromadb
import PyPDF2
from bs4 import BeautifulSoup
from chromadb.config import Settings

# ChromaDB Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "kronofogden"

# Target URLs
BASE_URL = "https://kronofogden.se"
SCRAPE_TARGETS = [
    {
        "name": "Föreskrifter, allmänna råd och meddelanden",
        "url": "https://kronofogden.se/om-kronofogden/dina-rattigheter-lagar-och-regler/foreskrifter-allmanna-rad-och-meddelanden",
        "category": "regulations",
    },
    {
        "name": "Handböcker",
        "url": "https://kronofogden.se/om-kronofogden/dina-rattigheter-lagar-och-regler/handbocker",
        "category": "handbooks",
    },
    {
        "name": "Statistik",
        "url": "https://kronofogden.se/om-kronofogden/statistik",
        "category": "statistics",
    },
    {
        "name": "Forskning",
        "url": "https://kronofogden.se/om-kronofogden/forskning",
        "category": "research",
    },
    {
        "name": "Vägledningar och ställningstaganden",
        "url": "https://kronofogden.se/om-kronofogden/dina-rattigheter-lagar-och-regler/vagledningar-och-stallningstaganden",
        "category": "guidance",
    },
    {
        "name": "Utredningar och rapporter",
        "url": "https://kronofogden.se/om-kronofogden/utredningar-och-rapporter",
        "category": "reports",
    },
    {
        "name": "Informationsmaterial",
        "url": "https://kronofogden.se/om-kronofogden/informationsmaterial",
        "category": "informationsmaterial",
    },
    {
        "name": "Uppdrag och värdegrund (Årsredovisningar)",
        "url": "https://kronofogden.se/om-kronofogden/uppdrag-och-vardegrund",
        "category": "annual_reports",
    },
    {
        "name": "Nyheter och press",
        "url": "https://kronofogden.se/om-kronofogden/nyheter-och-press",
        "category": "press",
    },
    {
        "name": "Blanketter och e-tjänster",
        "url": "https://kronofogden.se/e-tjanster-och-blanketter",
        "category": "forms",
    },
]


class KronofogdenScraper:
    """Scraper for Kronofogden documents"""

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.chroma_client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(allow_reset=False, anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish Government Documents"}
        )
        self.documents_found = []
        self.documents_scraped = 0
        self.errors = []

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=60)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def generate_doc_id(self, url: str, title: str) -> str:
        """Generate unique document ID"""
        content = f"{SOURCE_NAME}:{url}:{title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content with error handling"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    self.errors.append(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            self.errors.append(f"Fetch error for {url}: {e!s}")
            return None

    async def fetch_pdf(self, url: str) -> Optional[bytes]:
        """Fetch PDF content"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.read()
                return None
        except Exception as e:
            self.errors.append(f"PDF fetch error for {url}: {e!s}")
            return None

    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text from PDF bytes"""
        try:
            pdf_file = BytesIO(pdf_content)
            reader = PyPDF2.PdfReader(pdf_file)
            text_parts = []

            for page in reader.pages[:10]:  # First 10 pages for preview
                text_parts.append(page.extract_text())

            return "\n".join(text_parts)
        except Exception as e:
            self.errors.append(f"PDF extraction error: {e!s}")
            return ""

    def extract_pdf_links(self, html: str, base_url: str) -> list[dict]:
        """Extract all PDF links from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        pdf_links = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf") or "/download/" in href:
                full_url = urljoin(base_url, href)
                title = link.get_text(strip=True) or self.extract_title_from_context(link)

                pdf_links.append(
                    {"url": full_url, "title": title, "link_text": link.get_text(strip=True)}
                )

        return pdf_links

    def extract_title_from_context(self, link_element) -> str:
        """Extract title from surrounding context"""
        # Try parent heading
        parent = link_element.find_parent(["h1", "h2", "h3", "h4", "li", "div"])
        if parent:
            heading = parent.find(["h1", "h2", "h3", "h4"])
            if heading:
                return heading.get_text(strip=True)

        return "Dokument"

    def classify_document_type(self, title: str, url: str) -> str:
        """Classify document based on title and URL"""
        title_lower = title.lower()
        url_lower = url.lower()

        if "kfmfs" in title_lower or "föreskrift" in title_lower:
            return "KFMFS - Föreskrift"
        elif "kfm a" in title_lower or "allmänna råd" in title_lower:
            return "KFM A - Allmänt råd"
        elif "kfm m" in title_lower or "meddelande" in title_lower:
            return "KFM M - Meddelande"
        elif "handbok" in title_lower:
            return "Handbok"
        elif "årsredovisning" in title_lower:
            return "Årsredovisning"
        elif "rapport" in title_lower:
            return "Rapport"
        elif "statistik" in title_lower:
            return "Statistik"
        elif "forskning" in title_lower or "studie" in title_lower:
            return "Forskningspublikation"
        else:
            return "Informationsmaterial"

    def extract_year(self, text: str) -> Optional[str]:
        """Extract year from text (e.g., KFMFS 2024:1 -> 2024)"""
        year_match = re.search(r"\b(20\d{2})\b", text)
        return year_match.group(1) if year_match else None

    async def scrape_target(self, target: dict) -> int:
        """Scrape a single target URL"""
        print(f"\n[{target['category']}] Scraping: {target['name']}")
        print(f"URL: {target['url']}")

        html = await self.fetch_page(target["url"])
        if not html:
            return 0

        pdf_links = self.extract_pdf_links(html, target["url"])
        print(f"Found {len(pdf_links)} PDF links")

        count = 0
        for pdf_info in pdf_links:
            await self.process_document(pdf_info, target["category"])
            count += 1

        return count

    async def process_document(self, pdf_info: dict, category: str):
        """Process and store a single document"""
        url = pdf_info["url"]
        title = pdf_info["title"]

        # Generate unique ID
        doc_id = self.generate_doc_id(url, title)

        # Check if already exists
        try:
            existing = self.collection.get(ids=[doc_id])
            if existing["ids"]:
                print(f"  ✓ Exists: {title[:60]}")
                # Still count it in documents_found
                doc_type = self.classify_document_type(title, url)
                year = self.extract_year(title) or self.extract_year(url)
                self.documents_found.append(
                    {
                        "id": doc_id,
                        "title": title,
                        "type": doc_type,
                        "category": category,
                        "url": url,
                        "year": year,
                        "status": "existing",
                    }
                )
                return
        except:
            pass

        # Fetch PDF content
        pdf_content = await self.fetch_pdf(url)
        if not pdf_content:
            print(f"  ✗ Failed to fetch: {title[:60]}")
            return

        # Extract text
        text_content = self.extract_text_from_pdf(pdf_content)
        if not text_content:
            text_content = f"PDF Document: {title}"

        # Classify document
        doc_type = self.classify_document_type(title, url)
        year = self.extract_year(title) or self.extract_year(url)

        # Store in ChromaDB
        metadata = {
            "source": SOURCE_NAME,
            "category": category,
            "document_type": doc_type,
            "title": title,
            "url": url,
            "year": year or "unknown",
            "scraped_at": datetime.now().isoformat(),
            "link_text": pdf_info["link_text"],
        }

        try:
            self.collection.add(ids=[doc_id], documents=[text_content], metadatas=[metadata])
            self.documents_scraped += 1
            print(f"  ✓ Scraped: {title[:60]} ({doc_type})")

            self.documents_found.append(
                {
                    "id": doc_id,
                    "title": title,
                    "type": doc_type,
                    "category": category,
                    "url": url,
                    "year": year,
                }
            )

        except Exception as e:
            self.errors.append(f"Storage error for {title}: {e!s}")
            print(f"  ✗ Error: {title[:60]}: {e!s}")

    async def run(self):
        """Main scraping execution"""
        print("=" * 80)
        print("KRONOFOGDEN DOCUMENT SCRAPER")
        print("=" * 80)
        print(f"ChromaDB: {CHROMADB_PATH}")
        print(f"Collection: {COLLECTION_NAME}")
        print(f"Source: {SOURCE_NAME}")
        print(f"Targets: {len(SCRAPE_TARGETS)}")
        print("=" * 80)

        for target in SCRAPE_TARGETS:
            count = await self.scrape_target(target)
            await asyncio.sleep(1)  # Rate limiting

        return self.generate_report()

    def generate_report(self) -> dict:
        """Generate final JSON report"""
        # Count by document type
        type_counts = {}
        for doc in self.documents_found:
            doc_type = doc["type"]
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1

        # Count by year
        year_counts = {}
        for doc in self.documents_found:
            year = doc.get("year") or "unknown"
            year_counts[year] = year_counts.get(year, 0) + 1

        report = {
            "scraper": "Kronofogden Document Scraper",
            "timestamp": datetime.now().isoformat(),
            "source": SOURCE_NAME,
            "collection": COLLECTION_NAME,
            "chromadb_path": CHROMADB_PATH,
            "statistics": {
                "total_documents_scraped": self.documents_scraped,
                "total_documents_found": len(self.documents_found),
                "errors": len(self.errors),
                "targets_processed": len(SCRAPE_TARGETS),
            },
            "documents_by_type": type_counts,
            "documents_by_year": dict(sorted(year_counts.items(), reverse=True)),
            "documents": self.documents_found[:50],  # First 50 for report
            "errors": self.errors[:20],  # First 20 errors
            "flagged": len(self.documents_found) < 100,
        }

        return report


async def main():
    """Main execution"""
    async with KronofogdenScraper() as scraper:
        report = await scraper.run()

    # Print summary
    print("\n" + "=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
    print(f"Documents scraped: {report['statistics']['total_documents_scraped']}")
    print(f"Documents found: {report['statistics']['total_documents_found']}")
    print(f"Errors: {report['statistics']['errors']}")
    print(f"Flagged (< 100 docs): {report['flagged']}")

    print("\nDocuments by type:")
    for doc_type, count in report["documents_by_type"].items():
        print(f"  {doc_type}: {count}")

    print("\nDocuments by year:")
    for year, count in sorted(report["documents_by_year"].items(), reverse=True):
        print(f"  {year}: {count}")

    # Save report
    report_path = Path("kronofogden_scrape_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved: {report_path.absolute()}")

    if report["flagged"]:
        print("\n⚠️  WARNING: Document count below threshold (100)")
        print("Manual review recommended.")

    return report


if __name__ == "__main__":
    report = asyncio.run(main())
