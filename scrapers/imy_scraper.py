#!/usr/bin/env python3
"""
IMY (Integritetsskyddsmyndigheten) Document Scraper
Scrapar tillsynsbeslut, vägledningar, föreskrifter och GDPR-beslut från IMY
"""

import hashlib
import io
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import chromadb
import PyPDF2
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings


class IMYScraper:
    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.base_url = "https://www.imy.se"
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
        self.max_docs_per_type = 50  # Limit per document type

    def scrape_all(self) -> dict:
        """Main scraping orchestrator"""
        print("=" * 80)
        print("IMY SCRAPER - STARTING")
        print("=" * 80)

        # 1. Scrapa tillsynsbeslut
        print("\n[1/4] Scraping Tillsynsbeslut...")
        self.scrape_tillsynsbeslut()

        # 2. Scrapa GDPR-beslut
        print("\n[2/4] Scraping GDPR-beslut...")
        self.scrape_gdpr_beslut()

        # 3. Scrapa vägledningar
        print("\n[3/4] Scraping Vägledningar...")
        self.scrape_vagledningar()

        # 4. Scrapa föreskrifter
        print("\n[4/4] Scraping Föreskrifter...")
        self.scrape_foreskrifter()

        # Save to ChromaDB
        print("\n[FINAL] Saving to ChromaDB...")
        self.save_to_chromadb()

        # Generate report
        report = self.generate_report()
        return report

    def scrape_tillsynsbeslut(self):
        """Scrape supervision decisions from IMY"""
        urls = [
            f"{self.base_url}/tillsyner/",
            f"{self.base_url}/om-oss/aktuellt-fran-oss/praxisbeslut/",
        ]

        docs_count = 0
        for url in urls:
            if docs_count >= self.max_docs_per_type:
                break
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Look for decision links - more aggressive crawling
                for link in soup.find_all("a", href=True):
                    if docs_count >= self.max_docs_per_type:
                        break

                    href = link["href"]
                    text = link.get_text(strip=True)

                    # Look for beslut/decision patterns or internal pages
                    if any(
                        keyword in href.lower()
                        for keyword in ["beslut", "decision", "tillsyn", "/20"]
                    ) or any(
                        keyword in text.lower()
                        for keyword in ["beslut", "sanktion", "avgift", "tillsyn", "imy beslutar"]
                    ):
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls or not full_url.startswith(self.base_url):
                            continue

                        self.scraped_urls.add(full_url)

                        if href.endswith(".pdf"):
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": text or "Tillsynsbeslut",
                                    "content": pdf_text,
                                    "type": "tillsynsbeslut",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                docs_count += 1
                                print(f"  ✓ {text[:60]}")
                        else:
                            # Scrape the decision page
                            page_content = self.scrape_page(full_url)
                            if page_content and len(page_content) > 200:
                                doc = {
                                    "url": full_url,
                                    "title": text or "Tillsynsbeslut",
                                    "content": page_content,
                                    "type": "tillsynsbeslut",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                docs_count += 1
                                print(f"  ✓ {text[:60]}")

                        time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def scrape_gdpr_beslut(self):
        """Scrape GDPR decisions and sanctions"""
        urls = [
            f"{self.base_url}/tillsyner/",
            f"{self.base_url}/verksamhet/dataskydd/",
            f"{self.base_url}/privatperson/dataskydd/",
        ]

        for url in urls:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Get main page content first
                content = self.extract_content(soup)
                if content and len(content) > 300:
                    title = soup.find("h1")
                    title_text = title.get_text(strip=True) if title else "GDPR-beslut"

                    doc = {
                        "url": url,
                        "title": title_text,
                        "content": content,
                        "type": "gdpr_beslut",
                        "source": "imy",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.documents.append(doc)
                    print(f"  ✓ {title_text}")

                # Look for linked decisions
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    # GDPR/sanktion patterns
                    if any(
                        keyword in href.lower() or keyword in text.lower()
                        for keyword in ["sanktion", "gdpr", "dataskydd", "personuppgift"]
                    ):
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)

                        if href.endswith(".pdf"):
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": text or "GDPR-beslut",
                                    "content": pdf_text,
                                    "type": "gdpr_beslut",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")
                        else:
                            page_content = self.scrape_page(full_url)
                            if page_content and len(page_content) > 200:
                                doc = {
                                    "url": full_url,
                                    "title": text or "GDPR-beslut",
                                    "content": page_content,
                                    "type": "gdpr_beslut",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")

                        time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def scrape_vagledningar(self):
        """Scrape guidance documents"""
        urls = [
            f"{self.base_url}/vagledningar/",
            f"{self.base_url}/verksamhet/utbildning-och-stod/",
            f"{self.base_url}/privatperson/utbildning-och-stod/",
        ]

        for url in urls:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Get main content
                content = self.extract_content(soup)
                if content and len(content) > 300:
                    title = soup.find("h1")
                    title_text = title.get_text(strip=True) if title else "Vägledning"

                    doc = {
                        "url": url,
                        "title": title_text,
                        "content": content,
                        "type": "vägledning",
                        "source": "imy",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.documents.append(doc)
                    print(f"  ✓ {title_text}")

                # Look for linked guidance documents
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    if any(
                        keyword in text.lower()
                        for keyword in ["vägledning", "guide", "riktlinje", "råd", "handledning"]
                    ):
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)

                        if href.endswith(".pdf"):
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": text,
                                    "content": pdf_text,
                                    "type": "vägledning",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")
                        else:
                            page_content = self.scrape_page(full_url)
                            if page_content and len(page_content) > 200:
                                doc = {
                                    "url": full_url,
                                    "title": text,
                                    "content": page_content,
                                    "type": "vägledning",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")

                        time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def scrape_foreskrifter(self):
        """Scrape regulations (föreskrifter)"""
        urls = [
            f"{self.base_url}/om-oss/aktuellt-fran-oss/foreskrifter-och-allmanna-rad/",
        ]

        for url in urls:
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")

                # Get main content
                content = self.extract_content(soup)
                if content and len(content) > 300:
                    title = soup.find("h1")
                    title_text = title.get_text(strip=True) if title else "Föreskrifter"

                    doc = {
                        "url": url,
                        "title": title_text,
                        "content": content,
                        "type": "föreskrift",
                        "source": "imy",
                        "scraped_at": datetime.now().isoformat(),
                    }
                    self.documents.append(doc)
                    print(f"  ✓ {title_text}")

                # Look for regulation documents
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)

                    # DIFS pattern (IMY's regulation code) or föreskrift
                    if any(
                        keyword in text.lower() or keyword in href.lower()
                        for keyword in ["difs", "föreskrift", "reglering", "lagstiftning"]
                    ):
                        full_url = urljoin(self.base_url, href)

                        if full_url in self.scraped_urls:
                            continue

                        self.scraped_urls.add(full_url)

                        if href.endswith(".pdf"):
                            pdf_text = self.download_pdf(full_url)
                            if pdf_text:
                                doc = {
                                    "url": full_url,
                                    "title": text,
                                    "content": pdf_text,
                                    "type": "föreskrift",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")
                        else:
                            page_content = self.scrape_page(full_url)
                            if page_content and len(page_content) > 200:
                                doc = {
                                    "url": full_url,
                                    "title": text,
                                    "content": page_content,
                                    "type": "föreskrift",
                                    "source": "imy",
                                    "scraped_at": datetime.now().isoformat(),
                                }
                                self.documents.append(doc)
                                print(f"  ✓ {text[:60]}")

                        time.sleep(0.5)

            except Exception as e:
                print(f"  ✗ Error scraping {url}: {e}")

    def download_pdf(self, url: str) -> str | None:
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

    def scrape_page(self, url: str) -> str | None:
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
        for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
            script.decompose()

        # Try to find main content
        content_areas = [
            soup.find("article"),
            soup.find("main"),
            soup.find("div", class_=["main-content", "content-area", "content", "article-content"]),
            soup.find("div", id=["main", "content", "article"]),
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
            "agency": "imy",
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
    scraper = IMYScraper()
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
