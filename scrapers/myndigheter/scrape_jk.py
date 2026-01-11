#!/usr/bin/env python3
"""
JK (Justitiekanslern) Decision Scraper
Scrapes all decisions from jk.se and indexes to ChromaDB
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import chromadb
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class JKScraper:
    def __init__(self):
        self.base_url = "https://www.jk.se"
        self.decisions_url = f"{self.base_url}/beslut-och-yttranden/"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )

        # ChromaDB setup
        self.chroma_path = Path(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
        )
        self.chroma_path.mkdir(parents=True, exist_ok=True)

        # Initialize embedding model
        logger.info("Loading Swedish BERT model...")
        self.embedding_model = SentenceTransformer("KBLab/sentence-bert-swedish-cased")

        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_path), settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )

        self.stats = {
            "myndighet": "JK",
            "status": "OK",
            "docs_found": 0,
            "docs_indexed": 0,
            "errors": [],
            "start_time": datetime.now().isoformat(),
        }

    def get_year_links(self) -> list[str]:
        """Get all year pages from the main decisions page"""
        logger.info("Fetching year links...")
        try:
            response = self.session.get(self.decisions_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            year_links = []
            # Look for year links (2000-2025)
            for year in range(2000, 2026):
                year_url = f"{self.decisions_url}{year}/"
                year_links.append(year_url)

            logger.info(f"Found {len(year_links)} year pages to scrape")
            return year_links
        except Exception as e:
            logger.error(f"Error fetching year links: {e}")
            self.stats["errors"].append(f"Year links fetch error: {e!s}")
            return []

    def get_decision_links_from_year(self, year_url: str) -> list[str]:
        """Get all decision links from a specific year page"""
        logger.info(f"Fetching decisions from {year_url}")
        decision_links = []

        try:
            response = self.session.get(year_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all links matching the pattern /beslut-och-yttranden/YEAR/MONTH/DIARIENR/
            links = soup.find_all(
                "a", href=re.compile(r"/beslut-och-yttranden/\d{4}/\d{1,2}/[\w\d-]+/?")
            )

            for link in links:
                href = link.get("href")
                if href and not href.endswith("/beslut-och-yttranden/"):
                    full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                    if full_url not in decision_links:
                        decision_links.append(full_url)

            logger.info(f"Found {len(decision_links)} decisions in {year_url}")
            return decision_links

        except Exception as e:
            logger.error(f"Error fetching decisions from {year_url}: {e}")
            self.stats["errors"].append(f"Year page error ({year_url}): {e!s}")
            return []

    def extract_decision_metadata(self, soup: BeautifulSoup, url: str) -> dict | None:
        """Extract metadata from a decision page"""
        try:
            # Extract diary number from URL
            diary_match = re.search(r"/(\d{4}/\d{1,2}/[\w\d-]+)/?$", url)
            diary_number = diary_match.group(1).replace("/", "-") if diary_match else "unknown"

            # Extract title
            title_elem = soup.find("h1")
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"

            # Extract decision date
            date_elem = soup.find("time")
            decision_date = date_elem.get("datetime") if date_elem else None

            # Extract category from breadcrumbs or main content
            category = "unknown"
            breadcrumb = soup.find("nav", {"aria-label": "breadcrumb"})
            if breadcrumb:
                crumbs = breadcrumb.find_all("a")
                if len(crumbs) > 1:
                    category = crumbs[-1].get_text(strip=True)

            # Extract full text content
            main_content = (
                soup.find("main") or soup.find("article") or soup.find("div", class_="content")
            )
            text_content = ""

            if main_content:
                # Remove script and style elements
                for script in main_content(["script", "style"]):
                    script.decompose()
                text_content = main_content.get_text(separator="\n", strip=True)

            # Clean up text
            text_content = re.sub(r"\n\s*\n", "\n\n", text_content)
            text_content = text_content.strip()

            if not text_content or len(text_content) < 100:
                logger.warning(f"Short or empty content for {url}")
                return None

            return {
                "diary_number": diary_number,
                "title": title,
                "decision_date": decision_date,
                "category": category,
                "text": text_content,
                "url": url,
            }

        except Exception as e:
            logger.error(f"Error extracting metadata from {url}: {e}")
            self.stats["errors"].append(f"Metadata extraction error ({url}): {e!s}")
            return None

    def scrape_decision(self, url: str) -> dict | None:
        """Scrape a single decision page"""
        try:
            time.sleep(0.5)  # Rate limiting
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            metadata = self.extract_decision_metadata(soup, url)

            if metadata:
                self.stats["docs_found"] += 1
                return metadata
            return None

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.stats["errors"].append(f"Scrape error ({url}): {e!s}")
            return None

    def index_to_chromadb(self, decisions: list[dict]):
        """Index decisions to ChromaDB"""
        logger.info(f"Indexing {len(decisions)} decisions to ChromaDB...")

        for idx, decision in enumerate(decisions):
            try:
                # Create embedding
                embedding = self.embedding_model.encode(decision["text"]).tolist()

                # Prepare metadata
                metadata = {
                    "source": "jk",
                    "diary_number": decision["diary_number"],
                    "title": decision["title"],
                    "category": decision["category"],
                    "url": decision["url"],
                    "scraped_at": datetime.now().isoformat(),
                }

                if decision["decision_date"]:
                    metadata["decision_date"] = decision["decision_date"]

                # Add to collection
                self.collection.add(
                    ids=[f"jk-{decision['diary_number']}"],
                    embeddings=[embedding],
                    documents=[decision["text"]],
                    metadatas=[metadata],
                )

                self.stats["docs_indexed"] += 1

                if (idx + 1) % 10 == 0:
                    logger.info(f"Indexed {idx + 1}/{len(decisions)} decisions")

            except Exception as e:
                logger.error(
                    f"Error indexing decision {decision.get('diary_number', 'unknown')}: {e}"
                )
                self.stats["errors"].append(
                    f"Indexing error ({decision.get('diary_number')}): {e!s}"
                )

        logger.info(f"Indexing complete. Total indexed: {self.stats['docs_indexed']}")

    def run(self):
        """Main scraping orchestration"""
        logger.info("Starting JK scraping operation...")

        # Get all year links
        year_links = self.get_year_links()

        all_decision_links = []
        for year_url in year_links:
            decision_links = self.get_decision_links_from_year(year_url)
            all_decision_links.extend(decision_links)
            time.sleep(1)  # Rate limiting between years

        logger.info(f"Total decision links found: {len(all_decision_links)}")

        # Scrape all decisions
        decisions = []
        for idx, url in enumerate(all_decision_links):
            logger.info(f"Scraping {idx + 1}/{len(all_decision_links)}: {url}")
            decision = self.scrape_decision(url)
            if decision:
                decisions.append(decision)

            if (idx + 1) % 50 == 0:
                logger.info(f"Progress: {idx + 1}/{len(all_decision_links)} scraped")

        # Index to ChromaDB
        if decisions:
            self.index_to_chromadb(decisions)

        # Finalize stats
        self.stats["end_time"] = datetime.now().isoformat()

        # Flag if too few documents
        if self.stats["docs_found"] < 100:
            self.stats["status"] = "FLAGGAD"
            logger.warning(
                f"SIMON: JK verkar ha problem - only {self.stats['docs_found']} documents found"
            )

        # Save results
        output_file = Path(
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/jk_scrape_results.json"
        )
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {output_file}")

        return self.stats


def main():
    scraper = JKScraper()
    results = scraper.run()

    print("\n" + "=" * 60)
    print("JK SCRAPING RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
