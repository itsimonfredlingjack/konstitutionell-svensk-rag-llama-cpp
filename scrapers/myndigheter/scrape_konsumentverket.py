#!/usr/bin/env python3
"""
KONSUMENTVERKET SCRAPER
Samlar föreskrifter (KOVFS), vägledningar, rapporter
Lagrar i ChromaDB collection: swedish_gov_docs
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

# KONFIGURATION
BASE_URL = "https://www.konsumentverket.se"
CHROMADB_PATH = "./chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
SOURCE = "konsumentverket"

# HEADERS
HEADERS = {"User-Agent": "Swedish Government Document Harvester (Research/Archive Purpose)"}


class KonsumentverketScraper:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMADB_PATH)
        try:
            self.collection = self.client.get_collection(COLLECTION_NAME)
            print(f"✅ Connected to existing collection: {COLLECTION_NAME}")
        except:
            self.collection = self.client.create_collection(COLLECTION_NAME)
            print(f"✅ Created new collection: {COLLECTION_NAME}")

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
        """Scrape KOVFS föreskrifter"""
        print("\n🔍 Scraping Föreskrifter (KOVFS)...")

        # Main regulations page
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

            # Find all links that might be regulations
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(BASE_URL, href)

                # Look for KOVFS references or regulation patterns
                if any(
                    pattern in href.lower()
                    for pattern in ["kovfs", "foreskrift", "forordning", "regler"]
                ):
                    if full_url not in visited_urls:
                        visited_urls.add(full_url)

                        page_soup = self.fetch_page(full_url)
                        if page_soup:
                            text = self.extract_text(page_soup)
                            title = page_soup.find("h1")
                            title_text = (
                                title.get_text(strip=True) if title else link.get_text(strip=True)
                            )

                            docs.append(
                                {
                                    "url": full_url,
                                    "title": title_text,
                                    "text": text,
                                    "type": "föreskrift",
                                }
                            )
                            print(f"  📄 {title_text[:80]}...")

                        time.sleep(1)  # Rate limiting

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

            # Find guidance documents
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

                            docs.append(
                                {
                                    "url": full_url,
                                    "title": title_text,
                                    "text": text,
                                    "type": "vägledning",
                                }
                            )
                            print(f"  📘 {title_text[:80]}...")

                        time.sleep(1)

        return docs

    def scrape_rapporter(self) -> list[dict]:
        """Scrape rapporter och utredningar"""
        print("\n🔍 Scraping Rapporter...")

        # Note: Publikationer är på separat subdomain
        urls_to_check = [
            "https://publikationer.konsumentverket.se/",
        ]

        docs = []
        visited_urls = set()

        for start_url in urls_to_check:
            soup = self.fetch_page(start_url)
            if not soup:
                continue

            # Find reports
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(BASE_URL, href)

                if any(
                    pattern in href.lower() for pattern in ["rapport", "publikation", "utredning"]
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

                            # Check if this is substantial content
                            if len(text) > 200:
                                docs.append(
                                    {
                                        "url": full_url,
                                        "title": title_text,
                                        "text": text,
                                        "type": "rapport",
                                    }
                                )
                                print(f"  📊 {title_text[:80]}...")

                        time.sleep(1)

        return docs

    def scrape_sitemap(self) -> list[dict]:
        """Scrape from sitemap if available"""
        print("\n🔍 Checking sitemap...")

        sitemap_urls = [f"{BASE_URL}/sitemap.xml", f"{BASE_URL}/sitemap_index.xml"]

        docs = []

        for sitemap_url in sitemap_urls:
            try:
                response = self.session.get(sitemap_url, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "xml")
                    urls = soup.find_all("loc")

                    print(f"  Found {len(urls)} URLs in sitemap")

                    # Filter for relevant URLs
                    for url_tag in urls[:100]:  # Limit to first 100
                        url = url_tag.get_text()
                        if any(
                            kw in url.lower()
                            for kw in [
                                "kovfs",
                                "foreskrift",
                                "vagledning",
                                "rapport",
                                "publikation",
                            ]
                        ):
                            page_soup = self.fetch_page(url)
                            if page_soup:
                                text = self.extract_text(page_soup)
                                title = page_soup.find("h1")
                                title_text = title.get_text(strip=True) if title else "Untitled"

                                if len(text) > 200:
                                    docs.append(
                                        {
                                            "url": url,
                                            "title": title_text,
                                            "text": text,
                                            "type": "sitemap_document",
                                        }
                                    )
                                    print(f"  📄 {title_text[:80]}...")

                            time.sleep(1)
                    break
            except Exception as e:
                print(f"  Sitemap not available: {e}")
                continue

        return docs

    def save_to_chromadb(self, docs: list[dict]):
        """Save documents to ChromaDB"""
        if not docs:
            print("⚠️  No documents to save")
            return

        print(f"\n💾 Saving {len(docs)} documents to ChromaDB...")

        ids = []
        documents = []
        metadatas = []

        for doc in docs:
            doc_id = self.generate_doc_id(doc["url"])

            # Check if already exists
            try:
                existing = self.collection.get(ids=[doc_id])
                if existing["ids"]:
                    print(f"  ⏭️  Skipping duplicate: {doc['title'][:60]}...")
                    continue
            except:
                pass

            ids.append(doc_id)
            documents.append(doc["text"][:50000])  # Limit text length
            metadatas.append(
                {
                    "source": SOURCE,
                    "url": doc["url"],
                    "title": doc["title"][:500],
                    "doc_type": doc["type"],
                    "scraped_at": datetime.now().isoformat(),
                }
            )

        if ids:
            self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"✅ Saved {len(ids)} new documents")
        else:
            print("ℹ️  All documents already in database")

    def run(self):
        """Run complete scraping operation"""
        print("=" * 80)
        print("KONSUMENTVERKET SCRAPER")
        print("=" * 80)

        all_docs = []

        # 1. Scrape föreskrifter
        foreskrifter = self.scrape_foreskrifter()
        all_docs.extend(foreskrifter)

        # 2. Scrape vägledningar
        vagledningar = self.scrape_vagledningar()
        all_docs.extend(vagledningar)

        # 3. Scrape rapporter
        rapporter = self.scrape_rapporter()
        all_docs.extend(rapporter)

        # 4. Try sitemap (if above methods didn't yield enough)
        if len(all_docs) < 50:
            sitemap_docs = self.scrape_sitemap()
            all_docs.extend(sitemap_docs)

        # 5. Save to ChromaDB
        self.save_to_chromadb(all_docs)

        # 6. Generate report
        report = {
            "source": SOURCE,
            "scraped_at": datetime.now().isoformat(),
            "total_documents": len(all_docs),
            "by_type": {
                "föreskrift": len([d for d in all_docs if d["type"] == "föreskrift"]),
                "vägledning": len([d for d in all_docs if d["type"] == "vägledning"]),
                "rapport": len([d for d in all_docs if d["type"] == "rapport"]),
                "other": len(
                    [
                        d
                        for d in all_docs
                        if d["type"] not in ["föreskrift", "vägledning", "rapport"]
                    ]
                ),
            },
            "documents": [
                {
                    "title": doc["title"],
                    "url": doc["url"],
                    "type": doc["type"],
                    "length": len(doc["text"]),
                }
                for doc in all_docs
            ],
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
        print(f"Föreskrifter: {report['by_type']['föreskrift']}")
        print(f"Vägledningar: {report['by_type']['vägledning']}")
        print(f"Rapporter: {report['by_type']['rapport']}")
        print(f"Other: {report['by_type']['other']}")
        print(f"\nReport saved: {report_path}")

        # Flag if < 100 docs
        if report["total_documents"] < 100:
            print("\n⚠️  WARNING: Less than 100 documents collected!")
            print("Consider expanding URL patterns or checking site structure")

        return report


if __name__ == "__main__":
    scraper = KonsumentverketScraper()
    report = scraper.run()
