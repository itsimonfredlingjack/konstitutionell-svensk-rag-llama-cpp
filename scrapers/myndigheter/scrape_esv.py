#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - ESV (Ekonomistyrningsverket)
Scrapes ESVFS regulations, publications, and handledningar from esv.se
Indexes to ChromaDB collection: swedish_gov_docs
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
COLLECTION_NAME = "esv_docs"  # Separate collection to avoid dimension conflicts
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384 dims

# Scraping Configuration
BASE_URL = "https://www.esv.se"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.esv.se/",
}

# Document Sources
SOURCES = {
    # ESVFS Regulations (10 identified)
    "esvfa_2022_1": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20221/",
    "esvfa_2022_2": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20222/",
    "esvfa_2022_3": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20223/",
    "esvfa_2022_4": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20224/",
    "esvfa_2022_5": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20225/",
    "esvfa_2022_6": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20226/",
    "esvfa_2022_7": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20227/",
    "esvfa_2022_8": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20228/",
    "esvfa_2022_9": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20229/",
    "esvfa_2022_10": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-202210/",
    # Main pages
    "foreskrifter": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/",
    "publikationer": "https://www.esv.se/uppdrag-och-rapporter/publikationer/",
    "regeringsuppdrag": "https://www.esv.se/uppdrag-och-rapporter/regeringsuppdrag/",
    "ea_regelverket": "https://forum.esv.se/ea-regelverket/",
    "rapportering": "https://www.esv.se/kunskapsstod-och-regler/rapportering/",
}

# Output
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/esv_docs")
OUTPUT_DIR.mkdir(exist_ok=True)


class ESVScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.documents = []
        self.pdf_links = []
        self.html_pages = []
        self.processed_urls = set()

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
            if href.endswith(".pdf") or "pdf" in href.lower():
                full_url = urljoin(base_url, href)
                title = link.get_text(strip=True) or link.get("title", "Untitled")
                pdf_links.append({"url": full_url, "title": title, "source_page": base_url})
        return pdf_links

    def extract_document_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        """Extract publication/regulation links from a page"""
        doc_links = []

        # Strategy 1: Find ESVFS regulation links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if (
                "esvfa" in href.lower()
                or "foreskrifter" in href.lower()
                or "publikationer" in href.lower()
            ):
                full_url = urljoin(base_url, href)
                title = link.get_text(strip=True)
                if title and len(title) > 5:
                    doc_links.append({"url": full_url, "title": title, "type": "regulation"})

        # Strategy 2: Find publication year pages (2020-2025)
        for year in range(2020, 2026):
            year_links = soup.find_all("a", href=re.compile(f"publikationer/{year}"))
            for link in year_links:
                full_url = urljoin(base_url, link["href"])
                title = link.get_text(strip=True)
                if title and len(title) > 10:
                    doc_links.append({"url": full_url, "title": title, "type": "publication"})

        # Strategy 3: Find ESV document numbers (ESV 2024:XX)
        text = soup.get_text()
        esv_refs = re.findall(r"ESV \d{4}:\d+", text)
        for ref in esv_refs:
            # Try to find associated link
            links = soup.find_all("a", string=re.compile(ref))
            for link in links:
                if link.get("href"):
                    full_url = urljoin(base_url, link["href"])
                    doc_links.append({"url": full_url, "title": ref, "type": "esv_document"})

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
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()

        text = ""

        # Strategy 1: Look for main/article elements
        main_content = soup.find(["main", "article"])
        if main_content:
            text = main_content.get_text(separator="\n", strip=True)

        # Strategy 2: Look for content divs
        if not text or len(text) < 100:
            content_divs = soup.find_all(
                "div", class_=re.compile(r"content|article|main|body|text|publication")
            )
            if content_divs:
                text = "\n".join([div.get_text(separator="\n", strip=True) for div in content_divs])

        # Strategy 3: Extract all paragraphs
        if not text or len(text) < 100:
            paragraphs = soup.find_all(["p", "li", "td", "dd", "h1", "h2", "h3"])
            if paragraphs:
                text = "\n".join(
                    [
                        p.get_text(separator=" ", strip=True)
                        for p in paragraphs
                        if len(p.get_text(strip=True)) > 15
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
            "source": "esv",
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

        # Try to find ESVFA document number
        text = soup.get_text()
        esvfa_match = re.search(r"ESVFA \d{4}:\d+", text)
        if esvfa_match:
            metadata["document_number"] = esvfa_match.group()
            metadata["document_type"] = "ESVFS_regulation"

        # Try to find ESV report number
        esv_match = re.search(r"ESV \d{4}:\d+", text)
        if esv_match:
            metadata["esv_number"] = esv_match.group()
            metadata["document_type"] = "ESV_publication"

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
            try:
                self.collection.add(
                    ids=[chunk_id],
                    embeddings=[embedding],
                    documents=[chunk],
                    metadatas=[chunk_metadata],
                )
            except Exception as e:
                print(f"  Warning: Failed to index chunk {i}: {e}")

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
        if url in self.processed_urls:
            return {"success": False, "url": url, "reason": "already_processed"}

        print(f"\nScraping: {url}")
        self.processed_urls.add(url)

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
        if pdfs:
            print(f"  Found {len(pdfs)} PDF links")

        # Extract document links
        doc_links = self.extract_document_links(soup, url)
        result["doc_links_count"] = len(doc_links)
        for link in doc_links:
            if link["url"] not in self.processed_urls:
                self.html_pages.append(link)
        if doc_links:
            print(f"  Found {len(doc_links)} document links")

        # Extract and index main content
        text = self.extract_text_from_html(soup)
        if len(text) > 100:
            metadata = self.extract_metadata(soup, url)
            self.index_document(text, metadata)
            result["indexed"] = True
            result["text_length"] = len(text)
            print(f"  ✓ Indexed {len(text)} characters")
        else:
            print(f"  Skipping indexing (text too short: {len(text)} chars)")

        return result

    def crawl_publikationer_pages(self, max_pages: int = 10):
        """Crawl through paginated publikationer results"""
        print(f"\n[CRAWLING] Publications archive (max {max_pages} pages)...")

        for page_num in range(1, max_pages + 1):
            url = f"https://www.esv.se/uppdrag-och-rapporter/publikationer/?page={page_num}"
            print(f"  Page {page_num}: {url}")

            soup = self.fetch_page(url)
            if not soup:
                break

            # Find all publication links
            pub_links = soup.find_all("a", href=re.compile(r"/publikationer/\d{4}/"))
            found_any = False

            for link in pub_links:
                full_url = urljoin(BASE_URL, link["href"])
                if full_url not in self.processed_urls:
                    self.html_pages.append(
                        {"url": full_url, "title": link.get_text(strip=True), "type": "publication"}
                    )
                    found_any = True

            if not found_any:
                print("  No new publications found, stopping pagination")
                break

            time.sleep(1)

    def run_sweep(self) -> dict:
        """Main scraping orchestration"""
        print("=" * 60)
        print("OPERATION MYNDIGHETS-SWEEP - ESV")
        print("=" * 60)

        start_time = time.time()
        stats = {
            "start_time": datetime.now().isoformat(),
            "pages_scraped": 0,
            "pdfs_found": 0,
            "documents_indexed": 0,
            "errors": [],
        }

        # Step 1: Scrape ESVFS regulations
        print("\n[PHASE 1] Scraping ESVFS regulations...")
        for name, url in SOURCES.items():
            result = self.scrape_page(url)
            if result["success"]:
                stats["pages_scraped"] += 1
            else:
                if result.get("reason") != "already_processed":
                    stats["errors"].append(f"Failed to scrape {name}: {url}")
            time.sleep(1)

        # Step 2: Crawl publications archive
        print("\n[PHASE 2] Crawling publications archive...")
        self.crawl_publikationer_pages(max_pages=20)

        # Step 3: Follow discovered document links
        print(f"\n[PHASE 3] Following {len(self.html_pages)} discovered document links...")
        unique_urls = list({p["url"]: p for p in self.html_pages}.values())[:100]
        for link in unique_urls:
            if link["url"] not in self.processed_urls:
                result = self.scrape_page(link["url"])
                if result["success"]:
                    stats["pages_scraped"] += 1
                time.sleep(1)

        # Step 4: Download sample PDFs
        print(f"\n[PHASE 4] Processing {len(self.pdf_links[:30])} PDFs...")
        unique_pdfs = list({p["url"]: p for p in self.pdf_links}.values())[:30]
        for pdf in unique_pdfs:
            filename = Path(urlparse(pdf["url"]).path).name
            if not filename:
                filename = hashlib.md5(pdf["url"].encode()).hexdigest()[:12] + ".pdf"
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

        # Count ESV documents in collection
        try:
            esv_count = self.collection.count()
            stats["documents_indexed"] = esv_count
        except:
            stats["documents_indexed"] = 0

        # Flagging rule
        if stats["documents_indexed"] < 100:
            stats["warning"] = (
                f"🚩 ESV: Fewer than 100 documents indexed ({stats['documents_indexed']})"
            )

        return stats


def main():
    scraper = ESVScraper()
    stats = scraper.run_sweep()

    # Save report
    report_path = OUTPUT_DIR / f"esv_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("OPERATION COMPLETE - ESV")
    print("=" * 60)
    print(f"Pages scraped: {stats['pages_scraped']}")
    print(f"PDFs found: {stats['total_pdf_links']}")
    print(f"PDFs downloaded: {stats['pdfs_found']}")
    print(f"Documents indexed to ChromaDB: {stats['documents_indexed']}")
    print(f"Duration: {stats['duration_seconds']:.1f}s")
    print(f"Report saved: {report_path}")

    if "warning" in stats:
        print(f"\n{stats['warning']}")

    # Return JSON to stdout for easy parsing
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(stats, indent=2, ensure_ascii=False))

    return stats


if __name__ == "__main__":
    main()
