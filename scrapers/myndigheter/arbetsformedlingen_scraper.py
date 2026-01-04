#!/usr/bin/env python3
"""
ARBETSFÖRMEDLINGEN SCRAPER
Scrapar dokument från arbetsformedlingen.se och laddar i ChromaDB
"""

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup


class ArbetsformedlingenScraper:
    def __init__(self, chromadb_path: str, collection_name: str = "swedish_gov_docs"):
        self.base_url = "https://arbetsformedlingen.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        # ChromaDB setup
        self.client = chromadb.PersistentClient(path=chromadb_path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"description": "Swedish government documents"}
        )

        self.documents_found = []
        self.documents_scraped = 0
        self.errors = []

    def get_page(self, url: str, retries: int = 3) -> requests.Response:
        """Fetch page with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response
            except Exception as e:
                if attempt == retries - 1:
                    self.errors.append(f"Failed to fetch {url}: {e!s}")
                    raise
                time.sleep(2**attempt)

    def extract_text_from_html(self, html: str) -> str:
        """Extract clean text from HTML"""
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extract metadata from page"""
        metadata = {
            "source": "arbetsformedlingen",
            "url": url,
            "scraped_at": datetime.now().isoformat(),
        }

        # Try to find title
        title = soup.find("h1")
        if title:
            metadata["title"] = title.get_text(strip=True)
        else:
            title_tag = soup.find("title")
            metadata["title"] = title_tag.get_text(strip=True) if title_tag else url

        # Try to find publication date
        date_patterns = [
            {"class": re.compile(r"date|publish|created")},
            {"property": "article:published_time"},
            {"name": "date"},
        ]

        for pattern in date_patterns:
            date_elem = soup.find(attrs=pattern)
            if date_elem:
                date_text = date_elem.get("content") or date_elem.get_text(strip=True)
                metadata["publish_date"] = date_text
                break

        # Try to find document type
        if "/rapport" in url or "rapport" in metadata.get("title", "").lower():
            metadata["doc_type"] = "rapport"
        elif "/analys" in url or "analys" in metadata.get("title", "").lower():
            metadata["doc_type"] = "analys"
        elif "/prognos" in url or "prognos" in metadata.get("title", "").lower():
            metadata["doc_type"] = "prognos"
        elif "/statistik" in url or "statistik" in metadata.get("title", "").lower():
            metadata["doc_type"] = "statistik"
        else:
            metadata["doc_type"] = "allmän"

        return metadata

    def scrape_document_page(self, url: str) -> tuple[str, dict]:
        """Scrape a single document page"""
        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract text
            text = self.extract_text_from_html(response.text)

            # Extract metadata
            metadata = self.extract_metadata(soup, url)

            return text, metadata

        except Exception as e:
            self.errors.append(f"Error scraping {url}: {e!s}")
            return None, None

    def find_document_links(self) -> list[str]:
        """Find all document links on arbetsformedlingen.se"""
        document_links = set()

        # Key sections to search
        search_urls = [
            f"{self.base_url}/om-oss/press/pressmeddelanden",
            f"{self.base_url}/om-oss/var-verksamhet/statistik-och-publikationer",
            f"{self.base_url}/om-oss/var-verksamhet/statistik-och-publikationer/rapporter",
            f"{self.base_url}/om-oss/var-verksamhet/statistik-och-publikationer/analyser",
            f"{self.base_url}/download",
            f"{self.base_url}/for-arbetssokande/stod-och-service",
            f"{self.base_url}/for-arbetsgivare",
        ]

        for base_search_url in search_urls:
            try:
                print(f"Searching: {base_search_url}")
                response = self.get_page(base_search_url)
                soup = BeautifulSoup(response.content, "html.parser")

                # Find all links
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    full_url = urljoin(base_search_url, href)

                    # Filter for document-like URLs
                    if any(
                        keyword in full_url.lower()
                        for keyword in [
                            "/rapport",
                            "/analys",
                            "/publikation",
                            "/statistik",
                            "/prognos",
                            "/download",
                            ".pdf",
                            "/artikel",
                        ]
                    ):
                        if full_url.startswith(self.base_url):
                            document_links.add(full_url)

                time.sleep(1)  # Rate limiting

            except Exception as e:
                self.errors.append(f"Error searching {base_search_url}: {e!s}")
                continue

        return list(document_links)

    def scrape_sitemap(self) -> list[str]:
        """Try to scrape sitemap for additional URLs"""
        sitemap_urls = []
        sitemap_locations = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemap_index.xml",
            f"{self.base_url}/robots.txt",
        ]

        for sitemap_url in sitemap_locations:
            try:
                response = self.get_page(sitemap_url)

                if sitemap_url.endswith(".xml"):
                    # Parse XML sitemap
                    soup = BeautifulSoup(response.content, "xml")
                    for loc in soup.find_all("loc"):
                        url = loc.get_text(strip=True)
                        if any(
                            keyword in url.lower()
                            for keyword in [
                                "rapport",
                                "analys",
                                "publikation",
                                "statistik",
                                "prognos",
                            ]
                        ):
                            sitemap_urls.append(url)
                else:
                    # Parse robots.txt for sitemap references
                    for line in response.text.splitlines():
                        if line.startswith("Sitemap:"):
                            sitemap_urls.append(line.split(":", 1)[1].strip())

            except Exception as e:
                print(f"Could not fetch {sitemap_url}: {e}")
                continue

        return sitemap_urls

    def store_in_chromadb(self, text: str, metadata: dict):
        """Store document in ChromaDB"""
        try:
            # Create unique ID based on URL
            doc_id = hashlib.md5(metadata["url"].encode()).hexdigest()

            # Check if already exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    print(f"Document already exists: {metadata.get('title', metadata['url'])}")
                    return
            except:
                pass

            # Add to collection
            self.collection.add(documents=[text], metadatas=[metadata], ids=[doc_id])

            self.documents_scraped += 1
            print(f"Stored [{self.documents_scraped}]: {metadata.get('title', metadata['url'])}")

        except Exception as e:
            self.errors.append(f"Error storing in ChromaDB: {e!s}")

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 80)
        print("ARBETSFÖRMEDLINGEN SCRAPER - STARTING")
        print("=" * 80)

        # Step 1: Find document links
        print("\n[1/3] Finding document links...")
        document_links = self.find_document_links()
        print(f"Found {len(document_links)} potential document links")

        # Step 2: Try sitemap
        print("\n[2/3] Checking sitemap...")
        sitemap_links = self.scrape_sitemap()
        print(f"Found {len(sitemap_links)} additional links from sitemap")

        # Combine and deduplicate
        all_links = list(set(document_links + sitemap_links))
        print(f"\nTotal unique links to scrape: {len(all_links)}")

        # Step 3: Scrape documents
        print("\n[3/3] Scraping documents...")
        for i, url in enumerate(all_links, 1):
            print(f"\n[{i}/{len(all_links)}] Processing: {url}")

            text, metadata = self.scrape_document_page(url)

            if text and metadata and len(text.strip()) > 200:
                self.store_in_chromadb(text, metadata)
                self.documents_found.append(metadata)
            else:
                print(f"Skipped (insufficient content): {url}")

            # Rate limiting
            time.sleep(2)

        # Generate report
        report = self.generate_report()
        return report

    def generate_report(self) -> dict:
        """Generate final report"""
        report = {
            "source": "arbetsformedlingen",
            "scraped_at": datetime.now().isoformat(),
            "documents_found": len(self.documents_found),
            "documents_scraped": self.documents_scraped,
            "flag": self.documents_scraped < 100,
            "flag_reason": f"Only {self.documents_scraped} documents found (threshold: 100)"
            if self.documents_scraped < 100
            else None,
            "errors": self.errors,
            "documents": self.documents_found,
            "stats": {
                "by_type": self._count_by_field("doc_type"),
                "total_errors": len(self.errors),
            },
        }

        return report

    def _count_by_field(self, field: str) -> dict[str, int]:
        """Count documents by metadata field"""
        counts = {}
        for doc in self.documents_found:
            value = doc.get(field, "unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts


def main():
    """Main entry point"""
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/arbetsformedlingen_report.json"
    )

    scraper = ArbetsformedlingenScraper(chromadb_path)
    report = scraper.run()

    # Save report
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "=" * 80)
    print("SCRAPING COMPLETE")
    print("=" * 80)
    print(f"Documents found: {report['documents_found']}")
    print(f"Documents scraped: {report['documents_scraped']}")
    print(f"Errors: {report['stats']['total_errors']}")
    print(f"Flagged: {report['flag']}")
    if report["flag"]:
        print(f"Flag reason: {report['flag_reason']}")
    print(f"\nReport saved to: {output_path}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    main()
