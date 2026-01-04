#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - STATSKONTORET (Simple version)
Uses sitemap and direct URL patterns to find publications
"""

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class StatskontoretSimpleScraper:
    def __init__(self):
        self.base_url = "https://www.statskontoret.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        self.documents: list[dict] = []
        self.seen_urls: set[str] = set()

    def get_text_hash(self, text: str) -> str:
        """Generate unique ID from content"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def try_sitemap(self) -> list[str]:
        """Try to get URLs from sitemap"""
        urls = []
        sitemap_urls = [
            f"{self.base_url}/sitemap.xml",
            f"{self.base_url}/sitemapindex.xml",
            f"{self.base_url}/sitemap_index.xml",
        ]

        for sitemap_url in sitemap_urls:
            try:
                resp = self.session.get(sitemap_url, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)

                    # Handle both sitemap index and regular sitemap
                    for url_elem in root.findall(
                        ".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                    ):
                        url = url_elem.text
                        if "/publicerat/" in url:
                            urls.append(url)

                    if urls:
                        print(f"  Found {len(urls)} URLs in sitemap")
                        return urls

            except Exception as e:
                print(f"  Sitemap {sitemap_url} failed: {e}")
                continue

        return urls

    def discover_via_search_patterns(self) -> list[str]:
        """Try common URL patterns for Swedish government publications"""
        urls = []

        # Try year-based patterns
        current_year = datetime.now().year
        for year in range(2015, current_year + 1):
            # Common patterns for Swedish gov sites
            test_urls = [
                f"{self.base_url}/publicerat/{year}/",
                f"{self.base_url}/rapporter/{year}/",
            ]

            for test_url in test_urls:
                try:
                    resp = self.session.get(test_url, timeout=10)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for link in soup.find_all("a", href=True):
                            href = link["href"]
                            if "/publicerat/" in href:
                                full_url = urljoin(test_url, href)
                                if full_url not in self.seen_urls:
                                    urls.append(full_url)
                                    self.seen_urls.add(full_url)
                    time.sleep(0.5)
                except:
                    pass

        return urls

    def scrape_page_content(self, url: str) -> dict | None:
        """Scrape content from a page"""
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract title
            title = None
            if soup.h1:
                title = soup.h1.get_text(strip=True)
            elif soup.title:
                title = soup.title.string

            if not title or len(title) < 3:
                return None

            # Extract main content
            content_parts = []

            # Remove unwanted elements
            for tag in soup.find_all(["script", "style", "nav", "aside", "header", "footer"]):
                tag.decompose()

            # Try to find main content area
            main_content = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=re.compile(r"content|main", re.I))
            )

            if main_content:
                content_parts.append(main_content.get_text(separator="\n", strip=True))
            else:
                # Fallback to all paragraphs
                paragraphs = soup.find_all("p")
                content_parts = [
                    p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50
                ]

            full_text = "\n\n".join(content_parts)

            # Basic quality check
            if len(full_text) < 300:
                return None

            # Extract metadata
            metadata = {
                "url": url,
                "title": title,
                "scraped_at": datetime.now().isoformat(),
                "source": "statskontoret",
            }

            # Look for date patterns
            for pattern in [
                r"publicerad[:\s]+(\d{4}-\d{2}-\d{2})",
                r"publicerad[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
                r"datum[:\s]+(\d{4}-\d{2}-\d{2})",
                r"(\d{4}-\d{2}-\d{2})",
            ]:
                match = re.search(pattern, resp.text, re.IGNORECASE)
                if match:
                    metadata["published"] = match.group(1)
                    break

            # Look for PDF
            pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
            if pdf_link:
                metadata["pdf_url"] = urljoin(url, pdf_link["href"])

            return {"id": self.get_text_hash(url), "text": full_text, "metadata": metadata}

        except Exception as e:
            print(f"  Error scraping {url}: {e}")
            return None

    def run_sweep(self) -> dict:
        """Execute sweep"""
        start_time = time.time()

        print("🔍 Starting Statskontoret sweep (simple mode)...")

        # Step 1: Try sitemap
        print("\n📍 Step 1: Checking sitemap...")
        urls = self.try_sitemap()

        # Step 2: Try pattern discovery
        if len(urls) < 10:
            print("\n📍 Step 2: Pattern discovery...")
            pattern_urls = self.discover_via_search_patterns()
            urls.extend(pattern_urls)

        # Remove duplicates
        urls = list(set(urls))
        print(f"\n📊 Total URLs to scrape: {len(urls)}")

        # Step 3: Scrape each URL
        print("\n📍 Step 3: Scraping content...")
        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{len(urls)}] {url}")
            doc = self.scrape_page_content(url)
            if doc:
                self.documents.append(doc)
            time.sleep(1)

        duration = time.time() - start_time

        result = {
            "source": "statskontoret",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration, 2),
            "documents_scraped": len(self.documents),
            "urls_checked": len(urls),
            "documents": self.documents,
            "chromadb_ready": True,
        }

        return result


def main():
    scraper = StatskontoretSimpleScraper()
    result = scraper.run_sweep()

    # Save to JSON
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/statskontoret_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n✅ Sweep complete!")
    print(f"   Documents: {result['documents_scraped']}")
    print(f"   Duration: {result['duration_seconds']}s")
    print(f"   Output: {output_file}")

    # Show sample if we got docs
    if result["documents"]:
        print(f"\n📄 Sample: {result['documents'][0]['metadata']['title']}")

    return result


if __name__ == "__main__":
    main()
