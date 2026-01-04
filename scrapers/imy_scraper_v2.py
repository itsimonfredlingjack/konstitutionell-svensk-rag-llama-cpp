#!/usr/bin/env python3
"""
IMY (Integritetsskyddsmyndigheten) Document Scraper V2
Simplified focused scraper for tillsynsbeslut and GDPR decisions
"""

import hashlib
import io
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import chromadb
import PyPDF2
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings


class IMYScraperV2:
    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.base_url = "https://www.imy.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        # ChromaDB setup
        self.client = chromadb.PersistentClient(
            path=chromadb_path, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )

        self.documents = []
        self.scraped_urls = set()

    def scrape_all(self) -> dict:
        """Main scraping orchestrator"""
        print("=" * 80)
        print("IMY SCRAPER V2 - STARTING")
        print("=" * 80)

        # Focus on key pages
        print("\n[1/2] Scraping key decision pages...")
        self.scrape_decision_pages()

        print("\n[2/2] Scraping regulations page...")
        self.scrape_single_page(
            f"{self.base_url}/om-oss/aktuellt-fran-oss/foreskrifter-och-allmanna-rad/", "föreskrift"
        )

        # Save to ChromaDB
        print("\n[FINAL] Saving to ChromaDB...")
        self.save_to_chromadb()

        # Generate report
        report = self.generate_report()
        return report

    def scrape_decision_pages(self):
        """Scrape decision pages with pagination support"""
        # Start with main tillsyner page and paginate
        base_url = f"{self.base_url}/tillsyner/"

        # Scrape page 1
        self.scrape_decision_listing(base_url, max_links=50)

        # Try pagination (page=2, page=3, etc)
        for page_num in range(2, 10):  # Try pages 2-9
            page_url = f"{base_url}?page={page_num}"
            found = self.scrape_decision_listing(page_url, max_links=30)
            if not found:
                # Try alternative pagination format
                page_url = f"{base_url}/sida-{page_num}/"
                found = self.scrape_decision_listing(page_url, max_links=30)
                if not found:
                    break

        # Also scrape praxisbeslut
        self.scrape_decision_listing(
            f"{self.base_url}/om-oss/aktuellt-fran-oss/praxisbeslut/", max_links=30
        )

        # Scrape key guidance pages
        print("\n  Scraping guidance pages...")
        self.scrape_single_page(f"{self.base_url}/vagledningar/", "vägledning")
        self.scrape_single_page(f"{self.base_url}/verksamhet/dataskydd/", "vägledning")

    def scrape_decision_listing(self, url: str, max_links: int = 30) -> bool:
        """Scrape a listing page for decisions"""
        try:
            print(f"\n  Checking: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            links_found = 0

            # Find all article/decision links
            for link in soup.find_all("a", href=True):
                if links_found >= max_links:
                    break

                href = link["href"]
                text = link.get_text(strip=True)

                # Skip navigation, external links
                if not href or href.startswith("#") or "javascript:" in href:
                    continue

                full_url = urljoin(self.base_url, href)

                # Only internal IMY links
                if not full_url.startswith(self.base_url):
                    continue

                # Skip already scraped
                if full_url in self.scraped_urls:
                    continue

                # Look for decision-like content
                is_decision = any(
                    [
                        "/20" in href and len(href) > 20,  # Date pattern
                        any(
                            kw in text.lower() for kw in ["beslut", "sanktion", "avgift", "tillsyn"]
                        ),
                        any(kw in href.lower() for kw in ["beslut", "tillsyn", "sanktion"]),
                    ]
                )

                if not is_decision:
                    continue

                self.scraped_urls.add(full_url)

                # Scrape the decision
                if href.endswith(".pdf"):
                    pdf_text = self.download_pdf(full_url)
                    if pdf_text and len(pdf_text) > 200:
                        doc = {
                            "url": full_url,
                            "title": text[:200] or "Tillsynsbeslut",
                            "content": pdf_text[:10000],
                            "type": "tillsynsbeslut",
                            "source": "imy",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        self.documents.append(doc)
                        links_found += 1
                        print(f"  ✓ PDF: {text[:60]}")
                else:
                    page_content = self.scrape_page(full_url)
                    if page_content and len(page_content) > 200:
                        doc = {
                            "url": full_url,
                            "title": text[:200] or "Tillsynsbeslut",
                            "content": page_content[:10000],
                            "type": "tillsynsbeslut",
                            "source": "imy",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        self.documents.append(doc)
                        links_found += 1
                        print(f"  ✓ {text[:60]}")

                time.sleep(0.3)

            return links_found > 0

        except Exception as e:
            print(f"  ✗ Error scraping {url}: {e}")
            return False

    def scrape_single_page(self, url: str, doc_type: str):
        """Scrape a single comprehensive page"""
        try:
            print(f"\n  Scraping: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            content = self.extract_content(soup)
            if content and len(content) > 300:
                title = soup.find("h1")
                title_text = title.get_text(strip=True) if title else doc_type.capitalize()

                doc = {
                    "url": url,
                    "title": title_text[:200],
                    "content": content[:10000],
                    "type": doc_type,
                    "source": "imy",
                    "scraped_at": datetime.now().isoformat(),
                }
                self.documents.append(doc)
                print(f"  ✓ {title_text}")

            # Look for linked PDFs
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.endswith(".pdf"):
                    full_url = urljoin(self.base_url, href)

                    if full_url in self.scraped_urls:
                        continue

                    self.scraped_urls.add(full_url)
                    text = link.get_text(strip=True)

                    pdf_text = self.download_pdf(full_url)
                    if pdf_text and len(pdf_text) > 200:
                        doc = {
                            "url": full_url,
                            "title": text[:200] or doc_type.capitalize(),
                            "content": pdf_text[:10000],
                            "type": doc_type,
                            "source": "imy",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        self.documents.append(doc)
                        print(f"  ✓ PDF: {text[:60]}")

        except Exception as e:
            print(f"  ✗ Error: {e}")

    def download_pdf(self, url: str) -> Optional[str]:
        """Download and extract text from PDF"""
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()

            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text_parts = []
            for page in pdf_reader.pages[:20]:  # Limit to 20 pages
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            full_text = "\n\n".join(text_parts)
            return full_text if full_text.strip() else None

        except Exception as e:
            print(f"    ⚠ PDF error: {str(e)[:100]}")
            return None

    def scrape_page(self, url: str) -> Optional[str]:
        """Scrape text content from a webpage"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            return self.extract_content(soup)
        except Exception as e:
            print(f"    ⚠ Page error: {str(e)[:100]}")
            return None

    def extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from page"""
        # Remove noise
        for script in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
            script.decompose()

        # Try to find main content
        content_areas = [
            soup.find("article"),
            soup.find("main"),
            soup.find("div", class_=re.compile("content|article|main", re.I)),
            soup.find("div", id=re.compile("content|article|main", re.I)),
        ]

        for area in content_areas:
            if area:
                text = area.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    return text

        # Fallback
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)

        return ""

    def save_to_chromadb(self):
        """Save all documents to ChromaDB"""
        if not self.documents:
            print("  ⚠ No documents to save!")
            return

        for i, doc in enumerate(self.documents):
            try:
                doc_id = hashlib.md5(doc["url"].encode()).hexdigest()

                metadata = {
                    "source": doc["source"],
                    "url": doc["url"],
                    "title": doc["title"][:500],
                    "type": doc["type"],
                    "scraped_at": doc["scraped_at"],
                }

                self.collection.upsert(
                    ids=[doc_id], documents=[doc["content"]], metadatas=[metadata]
                )

                if (i + 1) % 10 == 0:
                    print(f"  ... saved {i + 1}/{len(self.documents)}")

            except Exception as e:
                print(f"  ✗ Error saving {doc['url']}: {e}")

        print(f"  ✓ Saved {len(self.documents)} documents to ChromaDB")

    def generate_report(self) -> dict:
        """Generate final report"""
        report = {
            "agency": "imy",
            "timestamp": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "by_type": {},
            "documents": [],
        }

        for doc in self.documents:
            doc_type = doc["type"]
            report["by_type"][doc_type] = report["by_type"].get(doc_type, 0) + 1

        for doc in self.documents:
            report["documents"].append(
                {
                    "url": doc["url"],
                    "title": doc["title"],
                    "type": doc["type"],
                    "content_length": len(doc["content"]),
                }
            )

        if len(self.documents) < 100:
            report["warning"] = (
                f"FLAGGED: Only {len(self.documents)} documents found (threshold: 100)"
            )

        return report


def main():
    scraper = IMYScraperV2()
    report = scraper.scrape_all()

    # Save report
    report_path = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/imy_report.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    print("\n" + "=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
    print(f"Total documents: {report['total_documents']}")
    print("\nBy type:")
    for doc_type, count in report["by_type"].items():
        print(f"  {doc_type}: {count}")

    if "warning" in report:
        print(f"\n⚠️  {report['warning']}")

    print(f"\nReport saved to: {report_path}")

    return report


if __name__ == "__main__":
    main()
