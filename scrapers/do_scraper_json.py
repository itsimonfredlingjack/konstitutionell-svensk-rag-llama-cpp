#!/usr/bin/env python3
"""
DO (Diskrimineringsombudsmannen) Scraper - JSON Output
Extracts decisions, reports, and guidance from do.se
Outputs to JSON (avoids ChromaDB segfault issue)
"""

import hashlib
import json
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup


class DOScraper:
    def __init__(self):
        self.base_url = "https://www.do.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        self.documents = []
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

    def fetch_page(self, url: str, retries: int = 3) -> BeautifulSoup | None:
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

        # Create document
        doc = {
            "id": f"do_{self.get_hash(url)}",
            "source": "do",
            "type": "decision",
            "title": title,
            "url": url,
            "date": date,
            "content": content,
            "scraped_at": datetime.now().isoformat(),
        }

        self.documents.append(doc)
        self.stats["decisions"] += 1
        print(f"✓ Scraped decision: {title[:60]}...")

    def scrape_publications(self):
        """Scrape publications/reports"""
        pub_url = f"{self.base_url}/om-do/publikationer"
        soup = self.fetch_page(pub_url)

        if not soup:
            return

        # Find publication links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/publikationer/" in href and not href.endswith(".pdf"):
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                pub_soup = self.fetch_page(full_url)
                if not pub_soup:
                    continue

                title_tag = pub_soup.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else full_url.split("/")[-1]

                content = self.extract_text_content(pub_soup)

                doc = {
                    "id": f"do_{self.get_hash(full_url)}",
                    "source": "do",
                    "type": "publication",
                    "title": title,
                    "url": full_url,
                    "content": content,
                    "scraped_at": datetime.now().isoformat(),
                }

                self.documents.append(doc)
                self.stats["publications"] += 1
                print(f"✓ Scraped publication: {title[:60]}...")

                time.sleep(1)

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
            visited = set()
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if section in href and href not in visited:
                    visited.add(href)
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

                    doc = {
                        "id": f"do_{self.get_hash(full_url)}",
                        "source": "do",
                        "type": "guidance",
                        "title": title,
                        "url": full_url,
                        "content": content,
                        "scraped_at": datetime.now().isoformat(),
                    }

                    self.documents.append(doc)
                    self.stats["guidance"] += 1
                    print(f"✓ Scraped guidance: {title[:60]}...")

                    time.sleep(1)

    def run(self, max_decisions: int = 100):
        """Execute full scraping workflow"""
        print("=" * 60)
        print("DO.SE SCRAPER - OPERATION MYNDIGHETS-SWEEP")
        print("=" * 60)

        # 1. Scrape decisions
        print("\n[1/3] Scraping decisions...")
        decision_urls = self.scrape_decisions_list()
        for i, url in enumerate(decision_urls[:max_decisions], 1):
            print(f"  [{i}/{min(max_decisions, len(decision_urls))}] Processing...")
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
        self.stats["total_docs"] = len(self.documents)

        return self.stats

    def save_output(
        self, output_dir: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data"
    ):
        """Save documents and stats to JSON files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save documents
        docs_path = f"{output_dir}/do_documents_{timestamp}.json"
        with open(docs_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Documents saved to: {docs_path}")

        # Save stats
        stats_path = f"{output_dir}/do_stats_{timestamp}.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)
        print(f"📊 Stats saved to: {stats_path}")

        return docs_path, stats_path


def main():
    scraper = DOScraper()
    stats = scraper.run(max_decisions=100)
    docs_path, stats_path = scraper.save_output()

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
        print("\n⚠️  WARNING: Less than 100 documents scraped!")
        print("   Consider expanding scraping scope or checking site structure.")
    else:
        print(f"\n✅ SUCCESS: {stats['total_docs']} documents scraped")

    print("\n📁 Output files:")
    print(f"   Docs:  {docs_path}")
    print(f"   Stats: {stats_path}")

    return stats


if __name__ == "__main__":
    main()
