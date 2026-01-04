#!/usr/bin/env python3
"""
ARBETSFÖRMEDLINGEN SCRAPER V2
Deep crawl av arbetsformedlingen.se med fokus på faktiska dokument
"""

import hashlib
import json
import re
import time
import warnings
from datetime import datetime
from urllib.parse import urljoin, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup


class ArbetsformedlingenScraperV2:
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
        self.visited_urls: set[str] = set()

        # Suppress XML parsing warnings
        warnings.filterwarnings("ignore", category=UserWarning)

    def get_page(self, url: str, retries: int = 3) -> requests.Response:
        """Fetch page with retry logic"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30, allow_redirects=True)
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

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "iframe"]):
            element.decompose()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean up
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

        # Title
        title = soup.find("h1") or soup.find("title")
        metadata["title"] = title.get_text(strip=True) if title else url

        # Date patterns
        date_elem = (
            soup.find(class_=re.compile(r"date|publish", re.I))
            or soup.find(attrs={"property": "article:published_time"})
            or soup.find(attrs={"name": "date"})
        )
        if date_elem:
            metadata["publish_date"] = date_elem.get("content") or date_elem.get_text(strip=True)

        # Document type
        url_lower = url.lower()
        title_lower = metadata["title"].lower()

        if "rapport" in url_lower or "rapport" in title_lower:
            metadata["doc_type"] = "rapport"
        elif "analys" in url_lower or "analys" in title_lower:
            metadata["doc_type"] = "analys"
        elif "prognos" in url_lower or "prognos" in title_lower:
            metadata["doc_type"] = "prognos"
        elif "statistik" in url_lower or "statistik" in title_lower:
            metadata["doc_type"] = "statistik"
        elif "press" in url_lower or "pressmeddelande" in title_lower:
            metadata["doc_type"] = "pressmeddelande"
        else:
            metadata["doc_type"] = "allmän"

        return metadata

    def parse_sitemap(self, sitemap_url: str) -> list[str]:
        """Parse sitemap XML and extract URLs"""
        urls = []
        try:
            print(f"  Parsing sitemap: {sitemap_url}")
            response = self.get_page(sitemap_url)

            # Try XML parsing first
            try:
                soup = BeautifulSoup(response.content, "xml")
            except:
                soup = BeautifulSoup(response.content, "html.parser")

            # Find all <loc> tags
            for loc in soup.find_all("loc"):
                url = loc.get_text(strip=True)
                urls.append(url)

            print(f"    Found {len(urls)} URLs")

        except Exception as e:
            print(f"    Error parsing sitemap: {e}")

        return urls

    def discover_pages_from_sitemap(self) -> list[str]:
        """Discover all pages from sitemap"""
        all_urls = []

        # Get main sitemap
        try:
            main_sitemap = f"{self.base_url}/sitemap.xml"
            print(f"Fetching main sitemap: {main_sitemap}")
            response = self.get_page(main_sitemap)

            try:
                soup = BeautifulSoup(response.content, "xml")
            except:
                soup = BeautifulSoup(response.content, "html.parser")

            # Find all sitemap references
            sitemaps = []
            for sitemap in soup.find_all("sitemap"):
                loc = sitemap.find("loc")
                if loc:
                    sitemaps.append(loc.get_text(strip=True))

            # Also find direct URLs
            for loc in soup.find_all("loc"):
                url = loc.get_text(strip=True)
                if not url.endswith(".xml"):
                    all_urls.append(url)

            print(f"Found {len(sitemaps)} sub-sitemaps and {len(all_urls)} direct URLs")

            # Parse sub-sitemaps (limit to relevant ones)
            relevant_keywords = ["om-oss", "press", "statistik", "publikation", "rapport"]

            for sitemap_url in sitemaps:
                # Skip image/job sitemaps
                if any(
                    skip in sitemap_url.lower()
                    for skip in ["bilder", "platsbanken", "yrke", "kommun", "lan"]
                ):
                    continue

                # Only process relevant sitemaps
                if (
                    any(keyword in sitemap_url.lower() for keyword in relevant_keywords)
                    or "atlas-sidor" in sitemap_url.lower()
                ):
                    urls = self.parse_sitemap(sitemap_url)
                    all_urls.extend(urls)

                time.sleep(0.5)

        except Exception as e:
            print(f"Error with main sitemap: {e}")

        return all_urls

    def crawl_page_for_links(
        self, url: str, max_depth: int = 2, current_depth: int = 0
    ) -> list[str]:
        """Crawl a page and extract relevant document links"""
        if current_depth >= max_depth or url in self.visited_urls:
            return []

        self.visited_urls.add(url)
        links = []

        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.content, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(url, href)

                # Must be same domain
                if not full_url.startswith(self.base_url):
                    continue

                # Filter for content pages (not navigation/system)
                path = urlparse(full_url).path.lower()

                # Skip unwanted patterns
                if any(
                    skip in path
                    for skip in [
                        "/platsbanken/",
                        "/jobb/",
                        "/lediga-jobb/",
                        "/hitta-yrken/",
                        ".xml",
                        ".jpg",
                        ".png",
                        ".gif",
                        ".css",
                        ".js",
                        "/login",
                        "/logout",
                        "/minside",
                        "/sok",
                    ]
                ):
                    continue

                # Include relevant patterns
                if any(
                    keyword in path
                    for keyword in [
                        "/om-oss/",
                        "/press/",
                        "/statistik",
                        "/publikation",
                        "/rapport",
                        "/analys",
                        "/prognos",
                        "/artikel",
                    ]
                ):
                    links.append(full_url)

            time.sleep(1)

        except Exception as e:
            print(f"  Error crawling {url}: {e}")

        return links

    def scrape_document(self, url: str) -> tuple[str, dict]:
        """Scrape a single document"""
        try:
            response = self.get_page(url)
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract text
            text = self.extract_text_from_html(response.text)

            # Skip if too short
            if len(text.strip()) < 300:
                return None, None

            # Extract metadata
            metadata = self.extract_metadata(soup, url)

            return text, metadata

        except Exception as e:
            self.errors.append(f"Error scraping {url}: {e!s}")
            return None, None

    def store_in_chromadb(self, text: str, metadata: dict):
        """Store document in ChromaDB"""
        try:
            doc_id = hashlib.md5(metadata["url"].encode()).hexdigest()

            # Check if exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    print(f"  Already exists: {metadata.get('title', '')[:60]}")
                    return
            except:
                pass

            # Add to collection
            self.collection.add(documents=[text], metadatas=[metadata], ids=[doc_id])

            self.documents_scraped += 1
            print(f"  [{self.documents_scraped}] Stored: {metadata.get('title', '')[:60]}")

        except Exception as e:
            self.errors.append(f"Error storing in ChromaDB: {e!s}")

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 80)
        print("ARBETSFÖRMEDLINGEN SCRAPER V2 - STARTING")
        print("=" * 80)

        # Step 1: Discover URLs from sitemap
        print("\n[1/4] Discovering pages from sitemap...")
        sitemap_urls = self.discover_pages_from_sitemap()
        print(f"Found {len(sitemap_urls)} URLs from sitemap")

        # Step 2: Crawl key landing pages
        print("\n[2/4] Crawling key landing pages...")
        seed_urls = [
            f"{self.base_url}/om-oss",
            f"{self.base_url}/om-oss/press",
            f"{self.base_url}/statistik",
        ]

        crawled_urls = []
        for seed_url in seed_urls:
            print(f"  Crawling: {seed_url}")
            try:
                links = self.crawl_page_for_links(seed_url, max_depth=2)
                crawled_urls.extend(links)
                time.sleep(1)
            except Exception as e:
                print(f"  Error: {e}")

        print(f"Found {len(crawled_urls)} URLs from crawling")

        # Step 3: Combine and deduplicate
        all_urls = list(set(sitemap_urls + crawled_urls))

        # Filter to relevant content
        filtered_urls = [
            url
            for url in all_urls
            if any(
                keyword in url.lower()
                for keyword in [
                    "/om-oss/",
                    "/press/",
                    "/statistik",
                    "/publikation",
                    "/rapport",
                    "/analys",
                    "/prognos",
                    "/artikel",
                    "/nyheter",
                ]
            )
        ]

        print(f"\n[3/4] Total URLs to scrape: {len(filtered_urls)}")

        # Step 4: Scrape documents
        print("\n[4/4] Scraping documents...")

        for i, url in enumerate(filtered_urls, 1):
            if i % 10 == 0:
                print(f"\nProgress: {i}/{len(filtered_urls)}")

            text, metadata = self.scrape_document(url)

            if text and metadata:
                self.store_in_chromadb(text, metadata)
                self.documents_found.append(metadata)

            time.sleep(1.5)  # Rate limiting

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
            "errors": self.errors[:20],  # Limit error list
            "error_count": len(self.errors),
            "documents": self.documents_found,
            "stats": {
                "by_type": self._count_by_field("doc_type"),
                "total_errors": len(self.errors),
            },
        }

        return report

    def _count_by_field(self, field: str) -> dict[str, int]:
        """Count documents by field"""
        counts = {}
        for doc in self.documents_found:
            value = doc.get(field, "unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts


def main():
    """Main entry point"""
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/arbetsformedlingen_report_v2.json"
    )

    scraper = ArbetsformedlingenScraperV2(chromadb_path)
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
    print(f"Errors: {report['error_count']}")
    print(f"Flagged: {report['flag']}")
    if report["flag"]:
        print(f"Flag reason: {report['flag_reason']}")
    print("\nDocument types:")
    for doc_type, count in report["stats"]["by_type"].items():
        print(f"  {doc_type}: {count}")
    print(f"\nReport saved to: {output_path}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    main()
