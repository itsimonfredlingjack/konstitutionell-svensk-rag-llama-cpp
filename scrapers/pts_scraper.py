#!/usr/bin/env python3
"""
PTS (Post- och telestyrelsen) Scraper
Target: pts.se - Föreskrifter (PTSFS), beslut, rapporter, statistik
"""

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup


class PTSScraper:
    def __init__(self, chromadb_path: str):
        self.base_url = "https://pts.se"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Research Bot - Swedish Government Document Archive"
            }
        )

        self.client = chromadb.PersistentClient(path=chromadb_path)
        self.collection = self.client.get_or_create_collection(
            name="swedish_gov_docs",
            metadata={"description": "Swedish government documents from multiple agencies"},
        )

        self.scraped_docs = []
        self.errors = []

    def scrape(self) -> dict:
        """Main scraping orchestrator"""
        print(f"[PTS] Starting scrape at {datetime.now()}")

        targets = [
            self.scrape_ptsfs(),  # Föreskrifter
            self.scrape_decisions(),  # Beslut
            self.scrape_reports(),  # Rapporter
            self.scrape_statistics(),  # Statistik
            self.scrape_general_docs(),  # Övriga dokument
        ]

        for target in targets:
            if target:
                self.scraped_docs.extend(target)
            time.sleep(1)  # Rate limiting

        # Insert to ChromaDB
        if self.scraped_docs:
            self._insert_to_chromadb()

        return self._generate_report()

    def scrape_ptsfs(self) -> list[dict]:
        """Scrape PTSFS regulations"""
        docs = []
        url = "https://pts.se/sv/bransch/regler/lagar-och-regler/ptsfs/"

        try:
            print(f"[PTS] Scraping PTSFS from {url}")
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find regulation links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text(strip=True)

                # Match PTSFS patterns (e.g., PTSFS 2024:1)
                if "PTSFS" in text or "ptsfs" in href.lower():
                    full_url = urljoin(self.base_url, href)

                    # Extract year and number
                    match = re.search(r"PTSFS\s*(\d{4}):(\d+)", text, re.IGNORECASE)
                    year = match.group(1) if match else None
                    number = match.group(2) if match else None

                    doc = {
                        "url": full_url,
                        "title": text,
                        "source": "pts",
                        "category": "ptsfs",
                        "doc_type": "regulation",
                        "year": year,
                        "number": number,
                        "scraped_at": datetime.now().isoformat(),
                    }

                    # Fetch full content
                    content = self._fetch_page_content(full_url)
                    if content:
                        doc["content"] = content
                        docs.append(doc)
                        print(f"  ✓ {text}")

        except Exception as e:
            self.errors.append(f"PTSFS scrape failed: {e}")
            print(f"[ERROR] {e}")

        return docs

    def scrape_decisions(self) -> list[dict]:
        """Scrape PTS decisions"""
        docs = []
        url = "https://pts.se/sv/bransch/regler/beslut/"

        try:
            print(f"[PTS] Scraping decisions from {url}")
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for decision listings
            for article in soup.find_all(
                ["article", "div"], class_=re.compile(r"(beslut|decision|item)", re.I)
            ):
                title_elem = article.find(["h2", "h3", "h4", "a"])
                link_elem = article.find("a", href=True)

                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    full_url = urljoin(self.base_url, link_elem["href"])

                    doc = {
                        "url": full_url,
                        "title": title,
                        "source": "pts",
                        "category": "decision",
                        "doc_type": "decision",
                        "scraped_at": datetime.now().isoformat(),
                    }

                    content = self._fetch_page_content(full_url)
                    if content:
                        doc["content"] = content
                        docs.append(doc)
                        print(f"  ✓ {title[:60]}")

        except Exception as e:
            self.errors.append(f"Decisions scrape failed: {e}")
            print(f"[ERROR] {e}")

        return docs

    def scrape_reports(self) -> list[dict]:
        """Scrape PTS reports"""
        docs = []
        url = "https://pts.se/sv/bransch/analys-och-rapporter/"

        try:
            print(f"[PTS] Scraping reports from {url}")
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find PDF reports
            for link in soup.find_all("a", href=re.compile(r"\.pdf$", re.I)):
                title = link.get_text(strip=True)
                full_url = urljoin(self.base_url, link["href"])

                if title:  # Skip empty links
                    doc = {
                        "url": full_url,
                        "title": title,
                        "source": "pts",
                        "category": "report",
                        "doc_type": "pdf",
                        "scraped_at": datetime.now().isoformat(),
                    }

                    # For PDFs, we store metadata only (no content extraction)
                    doc["content"] = f"PDF Report: {title}\nURL: {full_url}"
                    docs.append(doc)
                    print(f"  ✓ {title[:60]}")

        except Exception as e:
            self.errors.append(f"Reports scrape failed: {e}")
            print(f"[ERROR] {e}")

        return docs

    def scrape_statistics(self) -> list[dict]:
        """Scrape PTS statistics"""
        docs = []
        url = "https://pts.se/sv/bransch/analys-och-rapporter/statistik/"

        try:
            print(f"[PTS] Scraping statistics from {url}")
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find statistics pages
            for link in soup.find_all("a", href=True):
                href = link["href"]
                text = link.get_text(strip=True)

                if "statistik" in href.lower() and text:
                    full_url = urljoin(self.base_url, href)

                    doc = {
                        "url": full_url,
                        "title": text,
                        "source": "pts",
                        "category": "statistics",
                        "doc_type": "webpage",
                        "scraped_at": datetime.now().isoformat(),
                    }

                    content = self._fetch_page_content(full_url)
                    if content:
                        doc["content"] = content
                        docs.append(doc)
                        print(f"  ✓ {text[:60]}")

        except Exception as e:
            self.errors.append(f"Statistics scrape failed: {e}")
            print(f"[ERROR] {e}")

        return docs

    def scrape_general_docs(self) -> list[dict]:
        """Scrape general documents from main navigation"""
        docs = []

        # Target pages with document listings
        targets = [
            "https://pts.se/sv/bransch/",
            "https://pts.se/sv/privat/",
            "https://pts.se/sv/om-pts/",
        ]

        for url in targets:
            try:
                print(f"[PTS] Scraping general docs from {url}")
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")

                # Find all internal links
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    # Filter for pts.se internal pages only
                    if href.startswith("/") or "pts.se" in href:
                        full_url = urljoin(self.base_url, href)

                        # Skip non-content pages
                        if any(
                            skip in full_url
                            for skip in ["mailto:", "javascript:", "#", ".jpg", ".png"]
                        ):
                            continue

                        if text and len(text) > 10:  # Meaningful text only
                            doc = {
                                "url": full_url,
                                "title": text,
                                "source": "pts",
                                "category": "general",
                                "doc_type": "webpage",
                                "scraped_at": datetime.now().isoformat(),
                            }

                            content = self._fetch_page_content(full_url)
                            if content and len(content) > 200:  # Substantial content only
                                doc["content"] = content
                                docs.append(doc)
                                print(f"  ✓ {text[:60]}")

                time.sleep(1)

            except Exception as e:
                self.errors.append(f"General docs scrape failed for {url}: {e}")
                print(f"[ERROR] {e}")

        return docs

    def _fetch_page_content(self, url: str) -> Optional[str]:
        """Fetch and extract text content from a webpage"""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            # Get text content
            text = soup.get_text(separator="\n", strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            content = "\n".join(lines)

            return content if len(content) > 100 else None

        except Exception as e:
            print(f"  [WARN] Failed to fetch content from {url}: {e}")
            return None

    def _insert_to_chromadb(self):
        """Insert scraped documents to ChromaDB"""
        if not self.scraped_docs:
            return

        print(f"\n[ChromaDB] Inserting {len(self.scraped_docs)} documents...")

        ids = []
        documents = []
        metadatas = []

        for doc in self.scraped_docs:
            # Generate unique ID
            doc_id = f"pts_{hashlib.sha256(doc['url'].encode()).hexdigest()[:16]}"
            ids.append(doc_id)

            # Document text
            documents.append(doc.get("content", doc["title"]))

            # Metadata
            metadata = {k: v for k, v in doc.items() if k != "content" and v is not None}
            metadatas.append(metadata)

        try:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"  ✓ Inserted {len(ids)} documents to swedish_gov_docs")
        except Exception as e:
            self.errors.append(f"ChromaDB insertion failed: {e}")
            print(f"[ERROR] {e}")

    def _generate_report(self) -> dict:
        """Generate scraping report"""
        report = {
            "agency": "pts",
            "name": "Post- och telestyrelsen",
            "timestamp": datetime.now().isoformat(),
            "documents_scraped": len(self.scraped_docs),
            "categories": {},
            "errors": self.errors,
            "status": "completed" if len(self.scraped_docs) > 0 else "failed",
        }

        # Count by category
        for doc in self.scraped_docs:
            cat = doc.get("category", "unknown")
            report["categories"][cat] = report["categories"].get(cat, 0) + 1

        return report


def main():
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

    scraper = PTSScraper(chromadb_path)
    report = scraper.scrape()

    # Save report
    report_path = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/pts_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print("PTS SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Documents scraped: {report['documents_scraped']}")
    print(f"Categories: {report['categories']}")
    print(f"Errors: {len(report['errors'])}")
    print(f"Report saved: {report_path}")
    print(f"{'='*60}\n")

    # Output JSON for parsing
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
