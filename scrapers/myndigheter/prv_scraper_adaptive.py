#!/usr/bin/env python3
"""
PRV Adaptive Scraper - Discovers current site structure first
"""

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCE_NAME = "prv"
BASE_URL = "https://www.prv.se"


class PRVAdaptiveScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        self.documents = []
        self.seen_urls = set()
        self.valid_sections = []

    def generate_doc_id(self, url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_page(self, url: str) -> BeautifulSoup:
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"  ❌ {url}: {e}")
            return None

    def is_404(self, soup: BeautifulSoup) -> bool:
        """Check if page is 404"""
        if not soup:
            return True
        text = soup.get_text().lower()
        return "kan inte hitta sidan" in text or "page not found" in text

    def discover_structure(self) -> list[str]:
        """Discover current PRV site structure by starting from homepage"""
        print("\n🔍 Discovering PRV site structure...")

        soup = self.fetch_page(BASE_URL)
        if not soup:
            print("❌ Could not fetch homepage")
            return []

        # Find navigation links
        sections = set()

        # Look for main navigation
        nav = soup.find("nav") or soup.find("header")
        if nav:
            for a in nav.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(BASE_URL, href)

                # Only PRV internal links
                if BASE_URL in full_url:
                    sections.add(full_url)

        # Look for links containing keywords
        keywords = [
            "foreskrift",
            "publikation",
            "vagledning",
            "stod",
            "rapport",
            "statistik",
            "lagar",
            "regler",
            "dokument",
        ]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(BASE_URL, href)

            # Check if link text or URL contains keywords
            link_text = a.get_text().lower()
            if BASE_URL in full_url and any(
                kw in full_url.lower() or kw in link_text for kw in keywords
            ):
                sections.add(full_url)

        print(f"✅ Found {len(sections)} potential sections")

        # Validate sections (check they're not 404)
        valid = []
        for url in list(sections)[:30]:  # Limit to avoid too many requests
            soup = self.fetch_page(url)
            if soup and not self.is_404(soup):
                valid.append(url)
                print(f"  ✓ {url}")
            time.sleep(0.5)

        print(f"\n✅ {len(valid)} valid sections found")
        return valid

    def find_document_links(self, soup: BeautifulSoup, base_url: str) -> set[str]:
        """Find document links (PDF or pages)"""
        links = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(base_url, href)

            # PDF links
            if href.endswith(".pdf") or (
                BASE_URL in full_url
                and full_url not in self.seen_urls
                and len(urlparse(full_url).path.split("/")) >= 3
            ):
                links.add(full_url)

        return links

    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text"""
        # Remove noise
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|main|article"))
            or soup.find("body")
        )

        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict[str, Any]:
        """Extract metadata"""
        meta = {
            "url": url,
            "source": SOURCE_NAME,
            "scraped_at": datetime.now().isoformat(),
        }

        # Title
        h1 = soup.find("h1")
        title_tag = soup.find("title")
        if h1:
            meta["title"] = h1.get_text(strip=True)
        elif title_tag:
            meta["title"] = title_tag.get_text(strip=True)

        # Meta description
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            meta["description"] = desc["content"]

        # Date
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            meta["published_date"] = time_tag["datetime"]

        # Document type from URL
        url_lower = url.lower()
        if "foreskrift" in url_lower:
            meta["doc_type"] = "föreskrift"
        elif "vagledning" in url_lower or "stod" in url_lower:
            meta["doc_type"] = "vägledning"
        elif "statistik" in url_lower or "rapport" in url_lower:
            meta["doc_type"] = "rapport"
        elif "publikation" in url_lower:
            meta["doc_type"] = "publikation"
        elif url.endswith(".pdf"):
            meta["doc_type"] = "pdf"
        else:
            meta["doc_type"] = "information"

        return meta

    def scrape_page(self, url: str, depth: int = 0) -> dict[str, Any]:
        """Scrape a page"""
        if depth > 2 or url in self.seen_urls:
            return None

        self.seen_urls.add(url)
        print(f"  {'  ' * depth}📄 {url}")

        soup = self.fetch_page(url)
        if not soup or self.is_404(soup):
            return None

        # Extract content
        text = self.extract_text(soup)
        if len(text) < 100:
            return None

        meta = self.extract_metadata(soup, url)
        doc = {
            "id": self.generate_doc_id(url),
            "content": text[:10000],  # Limit size
            **meta,
        }

        # Find sub-documents (only first 2 levels)
        if depth < 2:
            links = self.find_document_links(soup, url)
            print(f"  {'  ' * depth}  → {len(links)} links")

            for link in list(links)[:15]:  # Limit per page
                if link.endswith(".pdf"):
                    # Add PDF metadata
                    pdf_doc = {
                        "id": self.generate_doc_id(link),
                        "url": link,
                        "source": SOURCE_NAME,
                        "doc_type": "pdf",
                        "title": link.split("/")[-1],
                        "content": f"PDF från PRV: {link.split('/')[-1]}",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.documents.append(pdf_doc)
                else:
                    # Recursively scrape
                    sub_doc = self.scrape_page(link, depth + 1)
                    if sub_doc:
                        self.documents.append(sub_doc)

                time.sleep(0.3)

        return doc

    def run(self) -> list[dict[str, Any]]:
        """Run full scrape"""
        print("\n🚀 PRV Adaptive Scraper Starting...")

        # Discover structure
        sections = self.discover_structure()

        if not sections:
            print("\n⚠️  No valid sections found!")
            return []

        # Scrape each section
        print(f"\n📂 Scraping {len(sections)} sections...\n")

        for url in sections:
            doc = self.scrape_page(url)
            if doc:
                self.documents.append(doc)
            time.sleep(1)

        print(f"\n✅ Total documents: {len(self.documents)}")
        return self.documents


def main():
    start_time = time.time()

    scraper = PRVAdaptiveScraper()
    documents = scraper.run()

    result = {
        "status": "success" if documents else "warning",
        "source": SOURCE_NAME,
        "documents_scraped": len(documents),
        "execution_time_seconds": round(time.time() - start_time, 2),
        "timestamp": datetime.now().isoformat(),
        "documents": documents,
    }

    if 0 < len(documents) < 100:
        result["flag"] = f"⚠️  Only {len(documents)} documents"

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = (
        f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/prv_scrape_{timestamp}.json"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Saved: {report_path}")

    # Print summary
    summary = {k: v for k, v in result.items() if k != "documents"}
    summary["sample_titles"] = [d.get("title", "N/A")[:80] for d in documents[:5]]
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    return report_path


if __name__ == "__main__":
    main()
