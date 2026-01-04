#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - SKATTEVERKET
Scrapes public documents from skatteverket.se and indexes to ChromaDB
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup
from sentence_transformers import SentenceTransformer

# ChromaDB Configuration
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "skatteverket_docs"  # Separate collection to avoid embedding dimension conflicts
EMBEDDING_MODEL = "KBLab/sentence-bert-swedish-cased"

# Scraping Configuration
BASE_URL = "https://www.skatteverket.se"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.skatteverket.se/",
}

# Document Sources
SOURCES = {
    "stallningstaganden_aldre": "https://www.skatteverket.se/funktioner/rattsinformation/arkivforrattsligvagledning/arkiv/stallningstaganden/aldre.4.69ef368911e1304a62580001943.html",
    "foretagare": "https://www.skatteverket.se/foretag.4.76a43be412206334b89800052908.html",
    "rattsinformation_arkiv": "https://www.skatteverket.se/funktioner/rattsinformation/arkivforrattsliginformation.4.24e174c9142bc79083467.html",
    "handledningar": "https://www.skatteverket.se/funktioner/rattsinformation/arkivforrattsliginformation/arkiv/handledningar.4.18e1b10334ebe8bc80005332.html",
    "allmannarad": "https://www.skatteverket.se/funktioner/rattsinformation/arkivforrattsliginformation/arkiv/allmannarad/2002.4.18e1b10334ebe8bc80005798.html",
    "foreskrifter": "https://www.skatteverket.se/funktioner/rattsinformation/arkivforrattsliginformation/arkiv/foreskrifter/2006.4.3d6c82f21107cfb119f80002302.html",
}

# Output
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/skatteverket_docs")
OUTPUT_DIR.mkdir(exist_ok=True)


class SkatteverketScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.documents = []
        self.pdf_links = []
        self.html_pages = []

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.chroma_client.get_collection(name=COLLECTION_NAME)
            print(f"✓ Using existing ChromaDB collection: {COLLECTION_NAME}")
        except:
            self.collection = self.chroma_client.create_collection(name=COLLECTION_NAME)
            print(f"✓ Created new ChromaDB collection: {COLLECTION_NAME}")

        # Initialize embedding model
        print(f"Loading embedding model: {EMBEDDING_MODEL}...")
        self.embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        print("✓ Embedding model loaded")

    def fetch_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse HTML page with retries"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return BeautifulSoup(response.content, "html.parser")
            except Exception as e:
                print(f"  Attempt {attempt+1}/{retries} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(2**attempt)
        return None

    def extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract all PDF links from a page"""
        pdf_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                full_url = urljoin(base_url, href)
                title = link.get_text(strip=True) or link.get("title", "Untitled")
                pdf_links.append({"url": full_url, "title": title, "source_page": base_url})
        return pdf_links

    def extract_document_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract document/article links from a page"""
        doc_links = []

        # Strategy 1: Find links in content areas
        content_areas = soup.find_all(
            ["article", "div"], class_=re.compile(r"content|article|document|post")
        )
        for area in content_areas:
            for link in area.find_all("a", href=True):
                href = link["href"]
                if any(
                    keyword in href.lower()
                    for keyword in [
                        "stallningstaganden",
                        "rattsinformation",
                        "vagledning",
                        "handledning",
                    ]
                ):
                    full_url = urljoin(base_url, href)
                    title = link.get_text(strip=True)
                    if title and len(title) > 5:
                        doc_links.append({"url": full_url, "title": title, "type": "document_link"})

        # Strategy 2: Find all internal skatteverket.se links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            full_url = urljoin(base_url, href)

            # Only include skatteverket.se links
            if "skatteverket.se" in full_url:
                title = link.get_text(strip=True)
                if title and len(title) > 10 and len(title) < 200:
                    doc_links.append({"url": full_url, "title": title, "type": "internal_link"})

        return doc_links

    def download_pdf(self, url: str, filename: str) -> Optional[Path]:
        """Download PDF file"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            filepath = OUTPUT_DIR / filename
            filepath.write_bytes(response.content)
            return filepath
        except Exception as e:
            print(f"  Failed to download {url}: {e}")
            return None

    def extract_text_from_html(self, soup: BeautifulSoup) -> str:
        """Extract main text content from HTML"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Try multiple strategies to find content
        text = ""

        # Strategy 1: Look for main/article elements
        main_content = soup.find(["main", "article"])
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)

        # Strategy 2: Look for content divs
        if not text or len(text) < 100:
            content_divs = soup.find_all(
                "div", class_=re.compile(r"content|article|main|body|text|document")
            )
            if content_divs:
                text = "\n".join([div.get_text(separator="\n", strip=True) for div in content_divs])

        # Strategy 3: Extract all paragraphs
        if not text or len(text) < 100:
            paragraphs = soup.find_all(["p", "li", "td", "dd"])
            if paragraphs:
                text = "\n".join(
                    [
                        p.get_text(separator=" ", strip=True)
                        for p in paragraphs
                        if len(p.get_text(strip=True)) > 20
                    ]
                )

        # Fallback: get all text
        if not text or len(text) < 50:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [
            line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 5
        ]
        return "\n".join(lines)

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract metadata from HTML page"""
        metadata = {
            "url": url,
            "source": "skatteverket",
            "scraped_at": datetime.now().isoformat(),
        }

        # Extract title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Extract meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            metadata["description"] = meta_desc.get("content", "")

        # Try to find document number (common in Swedish gov docs)
        text = soup.get_text()
        doc_num_match = re.search(r"(SKV|DNR)\s*[\d\-]+", text)
        if doc_num_match:
            metadata["document_number"] = doc_num_match.group()

        # Try to find date
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        if date_match:
            metadata["document_date"] = date_match.group()

        return metadata

    def index_document(self, text: str, metadata: dict):
        """Index document to ChromaDB"""
        # Generate document ID
        doc_id = hashlib.md5(metadata["url"].encode()).hexdigest()

        # Split text into chunks (max 512 tokens for embedding model)
        chunks = self.chunk_text(text, max_length=500)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{i}"
            chunk_metadata = metadata.copy()
            chunk_metadata["chunk_index"] = i
            chunk_metadata["total_chunks"] = len(chunks)

            # Generate embedding
            embedding = self.embedding_model.encode(chunk).tolist()

            # Add to ChromaDB
            self.collection.add(
                ids=[chunk_id],
                embeddings=[embedding],
                documents=[chunk],
                metadatas=[chunk_metadata],
            )

    def chunk_text(self, text: str, max_length: int = 500) -> list[str]:
        """Split text into chunks"""
        words = text.split()
        chunks = []
        current_chunk = []

        for word in words:
            current_chunk.append(word)
            if len(" ".join(current_chunk)) >= max_length:
                chunks.append(" ".join(current_chunk))
                current_chunk = []

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks if chunks else [text]

    def scrape_page(self, url: str) -> dict:
        """Scrape a single page and extract all useful content"""
        print(f"\nScraping: {url}")

        soup = self.fetch_page(url)
        if not soup:
            return {"success": False, "url": url}

        result = {
            "success": True,
            "url": url,
            "pdf_count": 0,
            "doc_links_count": 0,
            "indexed": False,
        }

        # Extract PDFs
        pdfs = self.extract_pdf_links(soup, url)
        result["pdf_count"] = len(pdfs)
        self.pdf_links.extend(pdfs)
        print(f"  Found {len(pdfs)} PDF links")

        # Extract document links
        doc_links = self.extract_document_links(soup, url)
        result["doc_links_count"] = len(doc_links)
        for link in doc_links:
            if link["url"] not in [d["url"] for d in self.html_pages]:
                self.html_pages.append(link)
        print(f"  Found {len(doc_links)} document links")

        # Extract and index main content
        text = self.extract_text_from_html(soup)
        if len(text) > 50:  # Lower threshold to catch more content
            metadata = self.extract_metadata(soup, url)
            self.index_document(text, metadata)
            result["indexed"] = True
            result["text_length"] = len(text)
            print(f"  ✓ Indexed {len(text)} characters")

        return result

    def run_sweep(self) -> dict:
        """Main scraping orchestration"""
        print("=" * 60)
        print("OPERATION MYNDIGHETS-SWEEP - SKATTEVERKET")
        print("=" * 60)

        start_time = time.time()
        stats = {
            "start_time": datetime.now().isoformat(),
            "pages_scraped": 0,
            "pdfs_found": 0,
            "documents_indexed": 0,
            "errors": [],
        }

        # Step 1: Scrape initial sources
        print("\n[PHASE 1] Scraping initial sources...")
        for name, url in SOURCES.items():
            result = self.scrape_page(url)
            if result["success"]:
                stats["pages_scraped"] += 1
            else:
                stats["errors"].append(f"Failed to scrape {name}: {url}")
            time.sleep(1)  # Be polite

        # Step 2: Follow document links (limited depth)
        print(f"\n[PHASE 2] Following {len(self.html_pages[:50])} document links...")
        unique_urls = list(set([p["url"] for p in self.html_pages[:50]]))  # Limit to first 50
        for url in unique_urls:
            if url not in [s for s in SOURCES.values()]:
                result = self.scrape_page(url)
                if result["success"]:
                    stats["pages_scraped"] += 1
                time.sleep(1)

        # Step 3: Download and process PDFs (sample)
        print(f"\n[PHASE 3] Processing {len(self.pdf_links[:20])} PDFs...")
        unique_pdfs = list({p["url"]: p for p in self.pdf_links}.values())[:20]  # Limit to first 20
        for pdf in unique_pdfs:
            filename = Path(urlparse(pdf["url"]).path).name
            downloaded = self.download_pdf(pdf["url"], filename)
            if downloaded:
                stats["pdfs_found"] += 1
                print(f"  ✓ Downloaded: {filename}")
            time.sleep(1)

        # Final stats
        stats["end_time"] = datetime.now().isoformat()
        stats["duration_seconds"] = time.time() - start_time
        stats["total_pdf_links"] = len(self.pdf_links)
        stats["total_html_pages"] = len(self.html_pages)
        stats["documents_indexed"] = self.collection.count()

        # Flagging rule
        if stats["documents_indexed"] < 100:
            stats["warning"] = (
                "SIMON: Skatteverket verkar ha problem - färre än 100 dokument indexerade"
            )

        return stats


def main():
    scraper = SkatteverketScraper()
    stats = scraper.run_sweep()

    # Save report
    report_path = (
        OUTPUT_DIR / f"skatteverket_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("OPERATION COMPLETE")
    print("=" * 60)
    print(f"Pages scraped: {stats['pages_scraped']}")
    print(f"PDFs found: {stats['total_pdf_links']}")
    print(f"PDFs downloaded: {stats['pdfs_found']}")
    print(f"Documents indexed to ChromaDB: {stats['documents_indexed']}")
    print(f"Duration: {stats['duration_seconds']:.1f}s")
    print(f"Report saved: {report_path}")

    if "warning" in stats:
        print(f"\n⚠️  {stats['warning']}")

    return stats


if __name__ == "__main__":
    main()
