#!/usr/bin/env python3
"""
Energimyndigheten Document Scraper
Scrapar föreskrifter, rapporter, statistik och vägledningar från Energimyndigheten
"""

import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import chromadb
import PyPDF2
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings


class EnergimyndighetenScraper:
    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.base_url = "https://www.energimyndigheten.se"
        self.webshop_url = "https://energimyndigheten.a-w2m.se"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
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
        print("ENERGIMYNDIGHETEN SCRAPER - STARTING")
        print("=" * 80)

        # 1. Scrapa föreskrifter (STEMFS)
        print("\n[1/4] Scraping Föreskrifter...")
        self.scrape_foreskrifter()

        # 2. Scrapa publikationer från webbshop
        print("\n[2/4] Scraping Publikationer...")
        self.scrape_publikationer()

        # 3. Scrapa statistik och rapporter
        print("\n[3/4] Scraping Statistik & Rapporter...")
        self.scrape_statistik()

        # 4. Scrapa vägledningar
        print("\n[4/4] Scraping Vägledningar...")
        self.scrape_vagledningar()

        # Save to ChromaDB
        print("\n[FINAL] Saving to ChromaDB...")
        self.save_to_chromadb()

        # Generate report
        report = self.generate_report()
        return report

    def scrape_foreskrifter(self):
        """Scrape all STEMFS regulations"""
        url = f"{self.base_url}/om-oss/foreskrifter/"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all regulation links (STEMFS pattern)
            stemfs_pattern = re.compile(r"STEMFS\s+\d{4}:\d+")

            # Look for links containing PDFs or regulation references
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True)
                href = link["href"]

                # Check if this is a STEMFS reference
                if stemfs_pattern.search(text) or "stemfs" in href.lower():
                    full_url = urljoin(self.base_url, href)

                    if full_url in self.scraped_urls:
                        continue

                    self.scraped_urls.add(full_url)

                    # Extract STEMFS number
                    stemfs_match = stemfs_pattern.search(text)
                    stemfs_id = stemfs_match.group(0) if stemfs_match else "Unknown"

                    # If it's a PDF, download and extract text
                    if href.endswith(".pdf"):
                        pdf_text = self.download_pdf(full_url)
                        if pdf_text:
                            doc = {
                                "url": full_url,
                                "title": text or stemfs_id,
                                "content": pdf_text,
                                "type": "föreskrift",
                                "stemfs_id": stemfs_id,
                                "source": "energimyndigheten",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            self.documents.append(doc)
                            print(f"  ✓ {stemfs_id}: {text[:60]}")
                    else:
                        # It's a page about the regulation
                        page_content = self.scrape_page(full_url)
                        if page_content:
                            doc = {
                                "url": full_url,
                                "title": text or stemfs_id,
                                "content": page_content,
                                "type": "föreskrift",
                                "stemfs_id": stemfs_id,
                                "source": "energimyndigheten",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            self.documents.append(doc)
                            print(f"  ✓ {stemfs_id}: {text[:60]}")

            # Also look in main content for embedded regulations
            content_div = soup.find("div", class_=["main-content", "content-area", "article"])
            if content_div:
                for heading in content_div.find_all(["h2", "h3", "h4"]):
                    text = heading.get_text(strip=True)
                    if stemfs_pattern.search(text):
                        # Get content until next heading
                        content_parts = []
                        for sibling in heading.find_next_siblings():
                            if sibling.name in ["h2", "h3", "h4"]:
                                break
                            content_parts.append(sibling.get_text(strip=True))

                        content = "\n".join(content_parts)
                        if content:
                            stemfs_match = stemfs_pattern.search(text)
                            stemfs_id = stemfs_match.group(0) if stemfs_match else "Unknown"

                            doc = {
                                "url": url,
                                "title": text,
                                "content": content,
                                "type": "föreskrift",
                                "stemfs_id": stemfs_id,
                                "source": "energimyndigheten",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            self.documents.append(doc)
                            print(f"  ✓ {stemfs_id}: {text[:60]}")

        except Exception as e:
            print(f"  ✗ Error scraping föreskrifter: {e}")

    def scrape_publikationer(self):
        """Scrape publications from the webshop"""
        # Try to find publication listings
        search_urls = [
            f"{self.webshop_url}/search.mvc",
            f"{self.webshop_url}/System/TemplateList.aspx?p=Arkitektkopia&l=t&view=672",
        ]

        for search_url in search_urls:
            try:
                response = self.session.get(search_url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Look for publication links (ER pattern: ER YYYY:XX)
                er_pattern = re.compile(r"ER\s+\d{4}:\d+")

                for link in soup.find_all("a", href=True):
                    text = link.get_text(strip=True)
                    href = link["href"]

                    if er_pattern.search(text) or "GetTemplateResource" in href:
                        full_url = urljoin(self.webshop_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)

                        # Extract ER number
                        er_match = er_pattern.search(text)
                        er_id = er_match.group(0) if er_match else "Unknown"

                        if ".pdf" in href.lower() or "GetTemplateResource" in href:
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": text or er_id,
                                    "content": pdf_text,
                                    "type": "rapport",
                                    "publication_id": er_id,
                                    "source": "energimyndigheten",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {er_id}: {text[:60]}")

            except Exception as e:
                print(f"  ✗ Error scraping {search_url}: {e}")
                continue

        # Also try direct category pages
        categories = [
            "/System/TemplateNavigate.aspx?p=Arkitektkopia&l=t&view=672&cat=/Energiläget",
            "/System/TemplateNavigate.aspx?p=Arkitektkopia&l=t&view=672&cat=/Klimat%20och%20utsl%C3%A4pp",
            "/System/TemplateNavigate.aspx?p=Arkitektkopia&l=t&view=672&cat=/Transporter",
            "/System/TemplateNavigate.aspx?p=Arkitektkopia&l=t&view=672&cat=/Elcertifikat",
        ]

        for category in categories:
            self.scrape_category(f"{self.webshop_url}{category}")

    def scrape_category(self, url: str):
        """Scrape a category page from webshop"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Look for document links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "GetTemplateResource" in href or href.endswith(".pdf"):
                    full_url = urljoin(self.webshop_url, href)

                    if full_url in self.scraped_urls:
                        continue

                    self.scraped_urls.add(full_url)
                    text = link.get_text(strip=True)

                    pdf_text = self.download_pdf(full_url)
                    if pdf_text:
                        doc = {
                            "url": full_url,
                            "title": text or "Untitled",
                            "content": pdf_text,
                            "type": "publikation",
                            "source": "energimyndigheten",
                            "scraped_at": datetime.now().isoformat(),
                        }
                        self.documents.append(doc)
                        print(f"  ✓ {text[:60]}")

        except Exception as e:
            print(f"  ✗ Error scraping category {url}: {e}")

    def scrape_statistik(self):
        """Scrape statistics and reports"""
        stats_urls = [
            f"{self.base_url}/statistik/statistik/",
            f"{self.base_url}/statistik/officiell-energistatistik/",
            f"{self.base_url}/energisystem-och-analys/nulaget-i-energisystemet/energilaget/",
        ]

        for url in stats_urls:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Get page content
                content = self.extract_content(soup)

                if content:
                    title = soup.find("h1")
                    title_text = title.get_text(strip=True) if title else "Statistik"

                    doc = {
                        "url": url,
                        "title": title_text,
                        "content": content,
                        "type": "statistik",
                        "source": "energimyndigheten",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.documents.append(doc)
                    print(f"  ✓ {title_text}")

                # Look for linked reports
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if href.endswith(".pdf"):
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)
                        text = link.get_text(strip=True)

                        pdf_text = self.download_pdf(full_url)
                        if pdf_text:
                            doc = {
                                "url": full_url,
                                "title": text or "Statistikrapport",
                                "content": pdf_text,
                                "type": "statistik",
                                "source": "energimyndigheten",
                                "scraped_at": datetime.now().isoformat(),
                            }
                            self.documents.append(doc)
                            print(f"  ✓ {text[:60]}")

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def scrape_vagledningar(self):
        """Scrape guidance documents"""
        # Vägledningar are often linked from various topic pages
        topic_urls = [
            f"{self.base_url}/fornybart/hallbarhetskriterier/",
            f"{self.base_url}/effektiv-energianvandning/effektiv-energianvandning/",
            f"{self.base_url}/klimat/transporter/",
        ]

        for url in topic_urls:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Look for guidance documents
                for link in soup.find_all("a", href=True):
                    text = link.get_text(strip=True).lower()
                    href = link["href"]

                    if "vägledning" in text or "guide" in text or "guidance" in text:
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)

                        if href.endswith(".pdf"):
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": link.get_text(strip=True),
                                    "content": pdf_text,
                                    "type": "vägledning",
                                    "source": "energimyndigheten",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {link.get_text(strip=True)[:60]}")
                        else:
                            page_content = self.scrape_page(full_url)
                            if page_content:
                                doc = {
                                    "url": full_url,
                                    "title": link.get_text(strip=True),
                                    "content": page_content,
                                    "type": "vägledning",
                                    "source": "energimyndigheten",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {link.get_text(strip=True)[:60]}")

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def download_pdf(self, url: str) -> Optional[str]:
        """Download and extract text from PDF"""
        try:
            response = self.session.get(url, timeout=60)
            response.raise_for_status()

            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text_parts = []
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

            full_text = "\n\n".join(text_parts)
            return full_text if full_text.strip() else None

        except Exception as e:
            print(f"    ⚠ PDF error ({url}): {e}")
            return None

    def scrape_page(self, url: str) -> Optional[str]:
        """Scrape text content from a webpage"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            return self.extract_content(soup)
        except Exception as e:
            print(f"    ⚠ Page error ({url}): {e}")
            return None

    def extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from page"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        # Try to find main content
        content_areas = [
            soup.find("article"),
            soup.find("main"),
            soup.find("div", class_=["main-content", "content-area", "content"]),
            soup.find("div", id=["main", "content"]),
        ]

        for area in content_areas:
            if area:
                text = area.get_text(separator="\n", strip=True)
                if len(text) > 100:  # Minimum content length
                    return text

        # Fallback: get body text
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)

        return ""

    def save_to_chromadb(self):
        """Save all documents to ChromaDB"""
        if not self.documents:
            print("  ⚠ No documents to save!")
            return

        # Ensure collection exists
        try:
            self.collection = self.client.get_or_create_collection(
                name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
            )
        except Exception as e:
            print(f"  ✗ Error getting collection: {e}")
            return

        for i, doc in enumerate(self.documents):
            try:
                # Create unique ID
                doc_id = hashlib.md5(doc["url"].encode()).hexdigest()

                # Prepare metadata
                metadata = {
                    "source": doc["source"],
                    "url": doc["url"],
                    "title": doc["title"][:500],  # ChromaDB has metadata limits
                    "type": doc["type"],
                    "scraped_at": doc["scraped_at"],
                }

                # Add optional fields
                if "stemfs_id" in doc:
                    metadata["stemfs_id"] = doc["stemfs_id"]
                if "publication_id" in doc:
                    metadata["publication_id"] = doc["publication_id"]

                # Add to collection
                self.collection.upsert(
                    ids=[doc_id],
                    documents=[doc["content"][:10000]],  # Limit content size
                    metadatas=[metadata],
                )

                if (i + 1) % 10 == 0:
                    print(f"  ... saved {i + 1}/{len(self.documents)}")

            except Exception as e:
                print(f"  ✗ Error saving document {doc['url']}: {e}")

        print(f"  ✓ Saved {len(self.documents)} documents to ChromaDB")

    def generate_report(self) -> dict:
        """Generate final report"""
        report = {
            "agency": "energimyndigheten",
            "timestamp": datetime.now().isoformat(),
            "total_documents": len(self.documents),
            "by_type": {},
            "documents": [],
        }

        # Count by type
        for doc in self.documents:
            doc_type = doc["type"]
            report["by_type"][doc_type] = report["by_type"].get(doc_type, 0) + 1

        # Add document list
        for doc in self.documents:
            report["documents"].append(
                {
                    "url": doc["url"],
                    "title": doc["title"],
                    "type": doc["type"],
                    "content_length": len(doc["content"]),
                }
            )

        # Flag if too few documents
        if len(self.documents) < 100:
            report["warning"] = (
                f"FLAGGED: Only {len(self.documents)} documents found (threshold: 100)"
            )

        return report


def main():
    scraper = EnergimyndighetenScraper()
    report = scraper.scrape_all()

    # Save report
    report_path = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/energimyndigheten_report.json"
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
