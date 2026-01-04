#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - ESV (Ekonomistyrningsverket) - SIMPLE VERSION
Scrapes ESVFS regulations and publications WITHOUT ChromaDB (avoids segfault)
Saves documents as JSON for later indexing
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Scraping Configuration
BASE_URL = "https://www.esv.se"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "sv-SE,sv;q=0.9",
}

# Document Sources
SOURCES = {
    # ESVFS Regulations
    "esvfa_2022_2": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20222/",
    "esvfa_2022_3": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20223/",
    "esvfa_2022_4": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20224/",
    "esvfa_2022_5": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20225/",
    "esvfa_2022_6": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20226/",
    "esvfa_2022_7": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20227/",
    "esvfa_2022_8": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20228/",
    "esvfa_2022_9": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-20229/",
    "esvfa_2022_10": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/esvfa-202210/",
    "foreskrifter": "https://www.esv.se/kunskapsstod-och-regler/regelverk/foreskrifter/",
    "publikationer": "https://www.esv.se/uppdrag-och-rapporter/publikationer/",
}

# Output
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/esv_docs")
OUTPUT_DIR.mkdir(exist_ok=True)


class ESVScraperSimple:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.documents = []
        self.pdf_links = []
        self.processed_urls = set()

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"  Failed: {e}")
            return None

    def extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        pdfs = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if href.endswith(".pdf"):
                pdfs.append(
                    {"url": urljoin(base_url, href), "title": link.get_text(strip=True) or "PDF"}
                )
        return pdfs

    def extract_text(self, soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        main = soup.find(["main", "article"])
        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        lines = [
            line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 5
        ]
        return "\n".join(lines)

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        metadata = {
            "url": url,
            "source": "esv",
            "scraped_at": datetime.now().isoformat(),
        }

        title = soup.find("title")
        if title:
            metadata["title"] = title.get_text(strip=True)

        text = soup.get_text()

        # ESVFA number
        esvfa = re.search(r"ESVFA \d{4}:\d+", text)
        if esvfa:
            metadata["document_number"] = esvfa.group()
            metadata["type"] = "regulation"

        # ESV report number
        esv_num = re.search(r"ESV \d{4}:\d+", text)
        if esv_num:
            metadata["esv_number"] = esv_num.group()
            metadata["type"] = "publication"

        return metadata

    def scrape_page(self, url: str) -> Optional[dict]:
        if url in self.processed_urls:
            return None

        print(f"Scraping: {url}")
        self.processed_urls.add(url)

        soup = self.fetch_page(url)
        if not soup:
            return None

        text = self.extract_text(soup)
        if len(text) < 100:
            print(f"  Skipped (too short: {len(text)} chars)")
            return None

        metadata = self.extract_metadata(soup, url)
        pdfs = self.extract_pdf_links(soup, url)
        self.pdf_links.extend(pdfs)

        doc = {
            **metadata,
            "text": text,
            "text_length": len(text),
            "pdfs": pdfs,
            "id": hashlib.md5(url.encode()).hexdigest(),
        }

        self.documents.append(doc)
        print(f"  ✓ Saved {len(text)} chars, {len(pdfs)} PDFs")

        return doc

    def download_pdf(self, url: str, filename: str) -> bool:
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            (OUTPUT_DIR / filename).write_bytes(r.content)
            return True
        except:
            return False

    def run(self):
        print("=" * 60)
        print("OPERATION MYNDIGHETS-SWEEP - ESV (SIMPLE)")
        print("=" * 60)

        start = time.time()

        # Phase 1: Scrape main sources
        print("\n[PHASE 1] Scraping main sources...")
        for name, url in SOURCES.items():
            self.scrape_page(url)
            time.sleep(1)

        # Phase 2: Crawl publications (limited)
        print("\n[PHASE 2] Crawling publications...")
        for page in range(1, 11):  # First 10 pages
            url = f"{SOURCES['publikationer']}?page={page}"
            soup = self.fetch_page(url)
            if not soup:
                break

            pub_links = soup.find_all("a", href=re.compile(r"/publikationer/202[0-9]/"))
            new_count = 0
            for link in pub_links:
                full_url = urljoin(BASE_URL, link["href"])
                if full_url not in self.processed_urls:
                    self.scrape_page(full_url)
                    new_count += 1
                    time.sleep(0.5)

            if new_count == 0:
                break

        # Phase 3: Download sample PDFs
        print(f"\n[PHASE 3] Downloading {min(len(self.pdf_links), 30)} PDFs...")
        unique_pdfs = list({p["url"]: p for p in self.pdf_links}.values())[:30]
        downloaded = 0
        for pdf in unique_pdfs:
            filename = Path(urlparse(pdf["url"]).path).name
            if self.download_pdf(pdf["url"], filename):
                downloaded += 1
                print(f"  ✓ {filename}")
            time.sleep(0.5)

        # Save results
        duration = time.time() - start

        report = {
            "source": "esv",
            "scraped_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "documents_scraped": len(self.documents),
            "pdfs_found": len(self.pdf_links),
            "pdfs_downloaded": downloaded,
            "documents": self.documents,
        }

        report_file = OUTPUT_DIR / f"esv_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print("OPERATION COMPLETE - ESV")
        print("=" * 60)
        print(f"Documents scraped: {len(self.documents)}")
        print(f"PDFs found: {len(self.pdf_links)}")
        print(f"PDFs downloaded: {downloaded}")
        print(f"Duration: {duration:.1f}s")
        print(f"Report: {report_file}")

        if len(self.documents) < 100:
            print(f"\n🚩 WARNING: Fewer than 100 documents scraped ({len(self.documents)})")

        return report


if __name__ == "__main__":
    scraper = ESVScraperSimple()
    scraper.run()
