#!/usr/bin/env python3
"""
DO (Diskrimineringsombudsmannen) Scraper
Extracts decisions, reports, and guidance from do.se
Stores in ChromaDB collection: swedish_gov_docs (source: "do")
"""

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Optional

import chromadb
import requests
from bs4 import BeautifulSoup


class DOScraper:
    def __init__(
        self,
        chroma_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.base_url = "https://www.do.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        # ChromaDB setup - use existing collection without embedding function
        self.client = chromadb.PersistentClient(path=chroma_path)

        # Get existing collection (already has default embedding function)
        self.collection = self.client.get_collection(name="swedish_gov_docs")

        self.stats = {
            "decisions": 0,
            "publications": 0,
            "guidance": 0,
            "errors": [],
            "start_time": datetime.now().isoformat(),
        }

    def get_hash(self, text: str) -> str:
        """Generate unique ID from text"""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def fetch_page(self, url: str, retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse HTML page"""
        for attempt in range(retries):
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except Exception as e:
                if attempt == retries - 1:
                    self.stats["errors"].append({"url": url, "error": str(e)})
                    return None
                time.sleep(2**attempt)
        return None

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extract main text content from page"""
        # Remove unwanted elements
        for elem in soup.find_all(["script", "style", "nav", "footer", "header"]):
            elem.decompose()

        # Try to find main content area
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find(class_=re.compile(r"content|main|article"))
        )

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Clean up whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()

    def scrape_decisions_list(self) -> list[str]:
        """Scrape decision list page and extract all decision URLs"""
        list_url = (
            f"{self.base_url}/rattsfall-beslut-lagar-stodmaterial/tvister-domar-tillsynsbeslut"
        )
        soup = self.fetch_page(list_url)

        if not soup:
            return []

        decision_urls = []

        # Find all links to individual decisions
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/tvister-domar-tillsynsbeslut/" in href and href.count("/") >= 4:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in decision_urls:
                    decision_urls.append(full_url)

        print(f"Found {len(decision_urls)} decision URLs")
        return decision_urls

    def scrape_decision(self, url: str):
        """Scrape individual decision document"""
        soup = self.fetch_page(url)
        if not soup:
            return

        # Extract metadata
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else url.split("/")[-1]

        # Extract date
        date_pattern = r"\d{1,2}\s+\w+\s+\d{4}"
        date_match = re.search(date_pattern, soup.get_text())
        date = date_match.group(0) if date_match else "Unknown"

        # Extract full content
        content = self.extract_text_content(soup)

        # Create document ID
        doc_id = f"do_{self.get_hash(url)}"

        # Store in ChromaDB
        try:
            self.collection.add(
                documents=[content],
                metadatas=[
                    {
                        "source": "do",
                        "type": "decision",
                        "title": title,
                        "url": url,
                        "date": date,
                        "scraped_at": datetime.now().isoformat(),
                    }
                ],
                ids=[doc_id],
            )
            self.stats["decisions"] += 1
            print(f"✓ Stored decision: {title[:60]}...")
        except Exception as e:
            self.stats["errors"].append({"url": url, "error": str(e)})
            print(f"✗ Error storing {url}: {e}")

    def scrape_publications(self):
        """Scrape publications/reports"""
        pub_url = f"{self.base_url}/om-do/publikationer"
        soup = self.fetch_page(pub_url)

        if not soup:
            return

        # Find publication links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/publikationer/" in href or href.endswith(".pdf"):
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                # Skip PDFs for now (would need separate handling)
                if full_url.endswith(".pdf"):
                    continue

                pub_soup = self.fetch_page(full_url)
                if not pub_soup:
                    continue

                title_tag = pub_soup.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else full_url.split("/")[-1]

                content = self.extract_text_content(pub_soup)
                doc_id = f"do_{self.get_hash(full_url)}"

                try:
                    self.collection.add(
                        documents=[content],
                        metadatas=[
                            {
                                "source": "do",
                                "type": "publication",
                                "title": title,
                                "url": full_url,
                                "scraped_at": datetime.now().isoformat(),
                            }
                        ],
                        ids=[doc_id],
                    )
                    self.stats["publications"] += 1
                    print(f"✓ Stored publication: {title[:60]}...")
                except Exception as e:
                    self.stats["errors"].append({"url": full_url, "error": str(e)})

                time.sleep(1)  # Rate limiting

    def scrape_guidance(self):
        """Scrape guidance materials (vägledningar)"""
        sections = [
            "/for-arbetsgivare-och-utbildningsanordnare",
            "/jobbet-skolan-samhallet",
            "/diskriminerad",
        ]

        for section in sections:
            url = f"{self.base_url}{section}"
            soup = self.fetch_page(url)
            if not soup:
                continue

            # Find all subpages in this section
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if section in href and href != section:
                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                    guide_soup = self.fetch_page(full_url)
                    if not guide_soup:
                        continue

                    title_tag = guide_soup.find("h1")
                    title = title_tag.get_text(strip=True) if title_tag else full_url.split("/")[-1]

                    content = self.extract_text_content(guide_soup)

                    # Only store if substantive content
                    if len(content) < 200:
                        continue

                    doc_id = f"do_{self.get_hash(full_url)}"

                    try:
                        self.collection.add(
                            documents=[content],
                            metadatas=[
                                {
                                    "source": "do",
                                    "type": "guidance",
                                    "title": title,
                                    "url": full_url,
                                    "scraped_at": datetime.now().isoformat(),
                                }
                            ],
                            ids=[doc_id],
                        )
                        self.stats["guidance"] += 1
                        print(f"✓ Stored guidance: {title[:60]}...")
                    except Exception as e:
                        self.stats["errors"].append({"url": full_url, "error": str(e)})

                    time.sleep(1)

    def run(self):
        """Execute full scraping workflow"""
        print("=" * 60)
        print("DO.SE SCRAPER - OPERATION MYNDIGHETS-SWEEP")
        print("=" * 60)

        # 1. Scrape decisions
        print("\n[1/3] Scraping decisions...")
        decision_urls = self.scrape_decisions_list()
        for i, url in enumerate(decision_urls[:50], 1):  # Limit to 50 for initial run
            print(f"  [{i}/{min(50, len(decision_urls))}] Processing...")
            self.scrape_decision(url)
            time.sleep(0.5)

        # 2. Scrape publications
        print("\n[2/3] Scraping publications...")
        self.scrape_publications()

        # 3. Scrape guidance
        print("\n[3/3] Scraping guidance materials...")
        self.scrape_guidance()

        # Final stats
        self.stats["end_time"] = datetime.now().isoformat()
        self.stats["total_docs"] = (
            self.stats["decisions"] + self.stats["publications"] + self.stats["guidance"]
        )

        return self.stats

    def save_stats(
        self,
        output_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scrapers/do_stats.json",
    ):
        """Save scraping statistics"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)
        print(f"\n📊 Stats saved to: {output_path}")


def main():
    scraper = DOScraper()
    stats = scraper.run()
    scraper.save_stats()

    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Decisions:    {stats['decisions']}")
    print(f"Publications: {stats['publications']}")
    print(f"Guidance:     {stats['guidance']}")
    print(f"Total:        {stats['total_docs']}")
    print(f"Errors:       {len(stats['errors'])}")
    print("=" * 60)

    # Flag if <100 docs
    if stats["total_docs"] < 100:
        print("⚠️  WARNING: Less than 100 documents scraped!")
        print("   Consider expanding scraping scope or checking site structure.")

    return stats


if __name__ == "__main__":
    main()
