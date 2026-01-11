#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - LANTMÄTERIET
Scrapes documents from lantmateriet.se and stores in ChromaDB
"""

import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import chromadb
import PyPDF2
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings

# Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE_NAME = "lantmateriet"
BASE_URL = "https://www.lantmateriet.se"
TEMP_DIR = "/tmp/lantmateriet_scrape"
MIN_DOCS_THRESHOLD = 100

# Known document sections
DOCUMENT_URLS = [
    # Föreskrifter
    "https://www.lantmateriet.se/sv/om-lantmateriet/Rattsinformation/Foreskrifter/",
    # Handböcker
    "https://www.lantmateriet.se/sv/om-lantmateriet/rattsinformation/handbocker/",
    # HMK - Handbok i mät- och kartfrågor
    "https://www.lantmateriet.se/sv/geodata/hmk---handbok-i-mat--och-kartfragor/",
    "https://www.lantmateriet.se/sv/geodata/hmk---handbok-i-mat--och-kartfragor/lasarkivet/",
    # Rapporter och publikationer
    "https://www.lantmateriet.se/sv/Kartor-och-geografisk-information/gps-geodesi-och-swepos/Om-geodesi/Rapporter-och-publikationer/",
    "https://www.lantmateriet.se/sv/Kartor-och-geografisk-information/gps-geodesi-och-swepos/Om-geodesi/Rapporter-och-publikationer/Publikationer/",
]

# Direct PDF links discovered
KNOWN_PDFS = [
    "https://www.lantmateriet.se/globalassets/om-lantmateriet/rattsinformation/handbocker/handbok-fbl.pdf",
    "https://www.lantmateriet.se/globalassets/om-lantmateriet/rattsinformation/handbocker/handbok-jb.pdf",
    "https://www.lantmateriet.se/globalassets/om-lantmateriet/rattsinformation/foreskrifter/lmfs133.pdf",
]


class LantmaterietScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Government Document Archiver; Constitutional AI Research)"}
        )

        self.chroma_client = chromadb.PersistentClient(
            path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
        )

        Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)

        self.stats = {
            "start_time": datetime.now().isoformat(),
            "pdfs_found": 0,
            "pdfs_downloaded": 0,
            "pdfs_processed": 0,
            "pdfs_stored": 0,
            "pdfs_skipped": 0,
            "errors": [],
            "documents": [],
        }

    def calculate_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of content"""
        return hashlib.sha256(content).hexdigest()

    def extract_pdf_links(self, url: str) -> list[str]:
        """Extract all PDF links from a webpage"""
        pdf_links = []

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find all links
            for link in soup.find_all("a", href=True):
                href = link["href"]

                # Convert relative to absolute
                absolute_url = urljoin(url, href)

                # Check if PDF
                if absolute_url.lower().endswith(".pdf"):
                    pdf_links.append(absolute_url)
                    self.stats["pdfs_found"] += 1

            print(f"  Found {len(pdf_links)} PDFs on {url}")

        except Exception as e:
            error_msg = f"Failed to scrape {url}: {e!s}"
            print(f"  ERROR: {error_msg}")
            self.stats["errors"].append(error_msg)

        return pdf_links

    def download_pdf(self, url: str) -> bytes | None:
        """Download PDF content"""
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()

            # Verify it's actually a PDF
            content_type = response.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
                raise ValueError(f"Not a PDF: {content_type}")

            self.stats["pdfs_downloaded"] += 1
            return response.content

        except Exception as e:
            error_msg = f"Failed to download {url}: {e!s}"
            print(f"  ERROR: {error_msg}")
            self.stats["errors"].append(error_msg)
            return None

    def extract_text_from_pdf(self, pdf_content: bytes) -> str:
        """Extract text content from PDF"""
        try:
            # Save to temp file
            temp_path = Path(TEMP_DIR) / f"temp_{int(time.time())}.pdf"
            temp_path.write_bytes(pdf_content)

            # Extract text
            text = ""
            with open(temp_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + "\n\n"

            # Cleanup
            temp_path.unlink()

            return text.strip()

        except Exception as e:
            print(f"  WARNING: Failed to extract text: {e!s}")
            return ""

    def get_document_metadata(self, url: str, content: bytes, text: str) -> dict:
        """Extract metadata from document"""

        # Parse filename
        filename = Path(urlparse(url).path).name

        # Determine document type
        doc_type = "unknown"
        if "foreskrift" in url.lower() or "lmfs" in filename.lower():
            doc_type = "föreskrift"
        elif "handbok" in url.lower():
            doc_type = "handbok"
        elif "hmk" in url.lower():
            doc_type = "hmk_handbok"
        elif "rapport" in url.lower() or "publikation" in url.lower():
            doc_type = "rapport"

        # Extract title from text or filename
        title = filename.replace(".pdf", "").replace("-", " ").title()
        lines = text.split("\n")[:10]
        for line in lines:
            if len(line.strip()) > 10 and len(line.strip()) < 200:
                title = line.strip()
                break

        # Try to extract year
        year = None
        year_match = re.search(r"(19|20)\d{2}", text[:2000])
        if year_match:
            year = year_match.group(0)

        return {
            "source": SOURCE_NAME,
            "url": url,
            "filename": filename,
            "doc_type": doc_type,
            "title": title,
            "year": year or "unknown",
            "scraped_at": datetime.now().isoformat(),
            "size_bytes": len(content),
            "page_count": text.count("\n\n"),  # Rough estimate
        }

    def store_document(self, doc_id: str, text: str, metadata: dict) -> bool:
        """Store document in ChromaDB"""
        try:
            # Check if already exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    print(f"  SKIP: Already in database: {metadata['filename']}")
                    self.stats["pdfs_skipped"] += 1
                    return False
            except:
                pass

            # Store in ChromaDB
            self.collection.add(ids=[doc_id], documents=[text], metadatas=[metadata])

            self.stats["pdfs_stored"] += 1
            return True

        except Exception as e:
            error_msg = f"Failed to store {metadata['url']}: {e!s}"
            print(f"  ERROR: {error_msg}")
            self.stats["errors"].append(error_msg)
            return False

    def process_pdf(self, url: str) -> bool:
        """Download, extract, and store a PDF document"""
        print(f"\n[{self.stats['pdfs_processed'] + 1}] Processing: {url}")

        # Download
        content = self.download_pdf(url)
        if not content:
            return False

        # Calculate hash for deduplication
        doc_id = self.calculate_hash(content)

        # Extract text
        text = self.extract_text_from_pdf(content)
        if not text:
            print("  WARNING: No text extracted, storing URL only")
            text = f"Document URL: {url}\nFilename: {Path(urlparse(url).path).name}"

        self.stats["pdfs_processed"] += 1

        # Get metadata
        metadata = self.get_document_metadata(url, content, text)

        # Store
        success = self.store_document(doc_id, text, metadata)

        if success:
            print(f"  SUCCESS: Stored {metadata['filename']} ({len(text)} chars)")
            self.stats["documents"].append(
                {
                    "url": url,
                    "filename": metadata["filename"],
                    "type": metadata["doc_type"],
                    "title": metadata["title"],
                }
            )

        # Rate limiting
        time.sleep(2)

        return success

    def run(self):
        """Main scraping workflow"""
        print("=" * 80)
        print("OPERATION MYNDIGHETS-SWEEP - LANTMÄTERIET")
        print("=" * 80)

        # Collect all PDF links
        all_pdfs = set()

        print("\n[1/3] Discovering documents...")

        # Scrape document index pages
        for url in DOCUMENT_URLS:
            print(f"\nScanning: {url}")
            pdfs = self.extract_pdf_links(url)
            all_pdfs.update(pdfs)
            time.sleep(1)

        # Add known PDFs
        all_pdfs.update(KNOWN_PDFS)

        print(f"\n[2/3] Found {len(all_pdfs)} unique PDF documents")

        # Process each PDF
        print("\n[3/3] Processing PDFs...")
        for pdf_url in sorted(all_pdfs):
            self.process_pdf(pdf_url)

        # Generate report
        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["duration_seconds"] = (
            datetime.fromisoformat(self.stats["end_time"])
            - datetime.fromisoformat(self.stats["start_time"])
        ).total_seconds()

        # Flag check
        if self.stats["pdfs_stored"] < MIN_DOCS_THRESHOLD:
            self.stats["flag"] = (
                f"WARNING: Only {self.stats['pdfs_stored']} documents stored (threshold: {MIN_DOCS_THRESHOLD})"
            )
            print(f"\n⚠️  {self.stats['flag']}")
        else:
            self.stats["flag"] = None

        # Save report
        report_path = (
            Path(TEMP_DIR) / f"lantmateriet_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        report_path.write_text(json.dumps(self.stats, indent=2, ensure_ascii=False))

        print("\n" + "=" * 80)
        print("SCRAPING COMPLETE")
        print("=" * 80)
        print(f"PDFs found:      {self.stats['pdfs_found']}")
        print(f"PDFs downloaded: {self.stats['pdfs_downloaded']}")
        print(f"PDFs processed:  {self.stats['pdfs_processed']}")
        print(f"PDFs stored:     {self.stats['pdfs_stored']}")
        print(f"PDFs skipped:    {self.stats['pdfs_skipped']} (already in DB)")
        print(f"Errors:          {len(self.stats['errors'])}")
        print(f"Duration:        {self.stats['duration_seconds']:.1f}s")
        print(f"\nReport saved to: {report_path}")
        print("=" * 80)

        return self.stats


def main():
    scraper = LantmaterietScraper()
    report = scraper.run()

    # Print JSON report to stdout for easy parsing
    print("\nJSON REPORT:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0 if report["flag"] is None else 1


if __name__ == "__main__":
    sys.exit(main())
