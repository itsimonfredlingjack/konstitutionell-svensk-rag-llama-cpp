#!/usr/bin/env python3
"""
KONSUMENTVERKET SCRAPER - JSON OUTPUT
Samlar föreskrifter (KOVFS), vägledningar, rapporter
Sparar till JSON (ChromaDB-import sker separat pga segfault)
"""

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# KONFIGURATION
BASE_URL = "https://www.konsumentverket.se"
SOURCE = "konsumentverket"

# HEADERS
HEADERS = {"User-Agent": "Swedish Government Document Harvester (Research/Archive Purpose)"}


class KonsumentverketScraper:
    def __init__(self):
        self.documents = []
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def generate_doc_id(self, url: str) -> str:
        """Generate unique doc ID from URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"❌ Failed to fetch {url}: {e}")
            return None

    def extract_text(self, soup: BeautifulSoup) -> str:
        """Extract main text content"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Try to find main content area
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile("content|main"))
        )

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def scrape_foreskrifter(self) -> list[dict]:
        """Scrape KOVFS föreskrifter och lagar"""
        print("\n🔍 Scraping Föreskrifter och Lagar...")

        urls_to_check = [
            f"{BASE_URL}/omrade/konsumentlagar/",
            f"{BASE_URL}/artikellista/mal-domar-och-forelagganden/",
        ]

        docs = []
        visited_urls = set()

        for start_url in urls_to_check:
            soup = self.fetch_page(start_url)
            if not soup:
                continue

            # Extract links from this page
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(BASE_URL, href)

                # Look for regulation/law related content
                if any(
                    pattern in href.lower()
                    for pattern in ["lag", "foreskrift", "kovfs", "dom", "mal", "forelaggande"]
                ):
                    if full_url not in visited_urls and full_url.startswith(BASE_URL):
                        visited_urls.add(full_url)

                        page_soup = self.fetch_page(full_url)
                        if page_soup:
                            text = self.extract_text(page_soup)
                            title = page_soup.find("h1")
                            title_text = (
                                title.get_text(strip=True) if title else link.get_text(strip=True)
                            )

                            if len(text) > 200:
                                docs.append(
                                    {
                                        "id": self.generate_doc_id(full_url),
                                        "url": full_url,
                                        "title": title_text,
                                        "text": text[:50000],
                                        "type": "föreskrift",
                                        "source": SOURCE,
                                    }
                                )
                                print(f"  📄 {title_text[:80]}...")

                        time.sleep(0.5)

        return docs

    def scrape_vagledningar(self) -> list[dict]:
        """Scrape vägledningar"""
        print("\n🔍 Scraping Vägledningar...")

        urls_to_check = [
            f"{BASE_URL}/om-oss/vagledning-for-konsumenter/",
            f"{BASE_URL}/samhalle/stod-till-kommunal-konsumentvagledning/",
        ]

        docs = []
        visited_urls = set()

        for start_url in urls_to_check:
            soup = self.fetch_page(start_url)
            if not soup:
                continue

            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(BASE_URL, href)

                if "vagledning" in href.lower() or "guide" in href.lower():
                    if full_url not in visited_urls and full_url.startswith(BASE_URL):
                        visited_urls.add(full_url)

                        page_soup = self.fetch_page(full_url)
                        if page_soup:
                            text = self.extract_text(page_soup)
                            title = page_soup.find("h1")
                            title_text = (
                                title.get_text(strip=True) if title else link.get_text(strip=True)
                            )

                            if len(text) > 200:
                                docs.append(
                                    {
                                        "id": self.generate_doc_id(full_url),
                                        "url": full_url,
                                        "title": title_text,
                                        "text": text[:50000],
                                        "type": "vägledning",
                                        "source": SOURCE,
                                    }
                                )
                                print(f"  📘 {title_text[:80]}...")

                        time.sleep(0.5)

        return docs

    def scrape_publikationer(self) -> list[dict]:
        """Scrape publikationer från publikationer.konsumentverket.se"""
        print("\n🔍 Scraping Publikationer...")

        docs = []
        visited_urls = set()

        pub_url = "https://publikationer.konsumentverket.se/"
        soup = self.fetch_page(pub_url)

        if soup:
            # Find all publication links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(pub_url, href)

                if full_url not in visited_urls and full_url.startswith(pub_url):
                    # Skip PDF links for now (would need PDF parsing)
                    if not href.endswith(".pdf"):
                        visited_urls.add(full_url)

                        page_soup = self.fetch_page(full_url)
                        if page_soup:
                            text = self.extract_text(page_soup)
                            title = page_soup.find("h1")
                            title_text = (
                                title.get_text(strip=True) if title else link.get_text(strip=True)
                            )

                            if len(text) > 200:
                                docs.append(
                                    {
                                        "id": self.generate_doc_id(full_url),
                                        "url": full_url,
                                        "title": title_text,
                                        "text": text[:50000],
                                        "type": "publikation",
                                        "source": SOURCE,
                                    }
                                )
                                print(f"  📊 {title_text[:80]}...")

                        time.sleep(0.5)

                        # Limit to avoid excessive scraping
                        if len(docs) > 50:
                            break

        return docs

    def scrape_rapporter_from_sitemap(self) -> list[dict]:
        """Scrape rapport pages from sitemap"""
        print("\n🔍 Scraping Rapporter från sitemap...")

        docs = []
        visited_urls = set()

        try:
            response = self.session.get(f"{BASE_URL}/sitemap.xml", timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "xml")
                urls = soup.find_all("loc")

                # Filter for rapport URLs
                rapport_urls = [
                    url.get_text() for url in urls if "rapport" in url.get_text().lower()
                ]

                print(f"  Found {len(rapport_urls)} rapport URLs")

                for url in rapport_urls[:100]:  # Limit to first 100
                    if url not in visited_urls:
                        visited_urls.add(url)

                        page_soup = self.fetch_page(url)
                        if page_soup:
                            text = self.extract_text(page_soup)
                            title = page_soup.find("h1")
                            title_text = title.get_text(strip=True) if title else "Rapport"

                            if len(text) > 200:
                                docs.append(
                                    {
                                        "id": self.generate_doc_id(url),
                                        "url": url,
                                        "title": title_text,
                                        "text": text[:50000],
                                        "type": "rapport",
                                        "source": SOURCE,
                                    }
                                )
                                print(f"  📊 {title_text[:80]}...")

                        time.sleep(0.5)

        except Exception as e:
            print(f"  Error scraping sitemap: {e}")

        return docs

    def scrape_key_pages(self) -> list[dict]:
        """Scrape important category pages"""
        print("\n🔍 Scraping Key Pages...")

        key_urls = [
            f"{BASE_URL}/omrade/konsumentlagar/",
            f"{BASE_URL}/artikellista/mal-domar-och-forelagganden/",
            f"{BASE_URL}/om-oss/vagledning-for-konsumenter/",
        ]

        docs = []

        for url in key_urls:
            soup = self.fetch_page(url)
            if soup:
                text = self.extract_text(soup)
                title = soup.find("h1")
                title_text = title.get_text(strip=True) if title else "Kategori"

                if len(text) > 200:
                    docs.append(
                        {
                            "id": self.generate_doc_id(url),
                            "url": url,
                            "title": title_text,
                            "text": text[:50000],
                            "type": "kategori",
                            "source": SOURCE,
                        }
                    )
                    print(f"  📁 {title_text[:80]}...")

            time.sleep(0.5)

        return docs

    def run(self):
        """Run complete scraping operation"""
        print("=" * 80)
        print("KONSUMENTVERKET SCRAPER (JSON OUTPUT)")
        print("=" * 80)

        all_docs = []

        # 1. Scrape key pages
        key_pages = self.scrape_key_pages()
        all_docs.extend(key_pages)

        # 2. Scrape föreskrifter och lagar
        foreskrifter = self.scrape_foreskrifter()
        all_docs.extend(foreskrifter)

        # 3. Scrape vägledningar
        vagledningar = self.scrape_vagledningar()
        all_docs.extend(vagledningar)

        # 4. Scrape publikationer
        publikationer = self.scrape_publikationer()
        all_docs.extend(publikationer)

        # 5. Scrape rapporter från sitemap
        rapporter = self.scrape_rapporter_from_sitemap()
        all_docs.extend(rapporter)

        # Generate report
        report = {
            "source": SOURCE,
            "scraped_at": datetime.now().isoformat(),
            "total_documents": len(all_docs),
            "by_type": {
                "kategori": len([d for d in all_docs if d["type"] == "kategori"]),
                "föreskrift": len([d for d in all_docs if d["type"] == "föreskrift"]),
                "vägledning": len([d for d in all_docs if d["type"] == "vägledning"]),
                "publikation": len([d for d in all_docs if d["type"] == "publikation"]),
                "rapport": len([d for d in all_docs if d["type"] == "rapport"]),
            },
            "documents": all_docs,
        }

        # Save report
        import os

        os.makedirs("./data", exist_ok=True)
        report_path = (
            f"./data/konsumentverket_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 80)
        print("SCRAPING COMPLETE")
        print("=" * 80)
        print(f"Total documents: {report['total_documents']}")
        print(f"Kategorier: {report['by_type']['kategori']}")
        print(f"Föreskrifter: {report['by_type']['föreskrift']}")
        print(f"Vägledningar: {report['by_type']['vägledning']}")
        print(f"Publikationer: {report['by_type']['publikation']}")
        print(f"Rapporter: {report['by_type']['rapport']}")
        print(f"\nReport saved: {report_path}")

        # Flag if < 100 docs
        if report["total_documents"] < 100:
            print("\n⚠️  WARNING: Less than 100 documents collected!")
            print("Consider expanding search scope or checking site structure")
        else:
            print("\n✅ SUCCESS: Document collection complete")

        return report


if __name__ == "__main__":
    scraper = KonsumentverketScraper()
    report = scraper.run()
