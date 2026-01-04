#!/usr/bin/env python3
"""
JK (Justitiekanslern) Decision Scraper - Selenium Edition
Scrapes ALL decisions from jk.se using browser automation and indexes to ChromaDB
"""

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import chromadb
from bs4 import BeautifulSoup
from chromadb.config import Settings
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sentence_transformers import SentenceTransformer
from webdriver_manager.chrome import ChromeDriverManager

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class JKSeleniumScraper:
    def __init__(self):
        self.base_url = "https://www.jk.se"
        self.search_url = f"{self.base_url}/beslut-och-yttranden/"

        # Setup Chrome options
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        # Setup ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

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

    def get_all_decision_links(self) -> list[str]:
        """Get all decision links by clicking 'Visa fler' until no more exist"""
        logger.info("Loading decisions page and clicking 'Visa fler'...")

        try:
            self.driver.get(self.search_url)
            time.sleep(3)  # Let page load

            decision_links = set()
            clicks = 0
            max_clicks = 500  # Safety limit

            while clicks < max_clicks:
                # Extract all current decision links
                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                links = soup.find_all(
                    "a", href=re.compile(r"/beslut-och-yttranden/\d{4}/\d{1,2}/[\w\d-]+/?")
                )

                for link in links:
                    href = link.get("href")
                    if href and not href.endswith("/beslut-och-yttranden/"):
                        full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                        decision_links.add(full_url)

                logger.info(f"Click {clicks}: Found {len(decision_links)} unique decisions so far")

                # Try to find and click "Visa fler" button
                try:
                    # Look for button with text "Visa fler" or similar
                    show_more_button = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(
                            (
                                By.XPATH,
                                "//a[contains(text(), 'Visa fler')] | //button[contains(text(), 'Visa fler')]",
                            )
                        )
                    )

                    # Scroll to button
                    self.driver.execute_script("arguments[0].scrollIntoView();", show_more_button)
                    time.sleep(1)

                    # Click button
                    show_more_button.click()
                    time.sleep(2)  # Wait for new content to load

                    clicks += 1

                except TimeoutException:
                    logger.info("No more 'Visa fler' button found. All decisions loaded.")
                    break
                except Exception as e:
                    logger.warning(f"Error clicking 'Visa fler': {e}")
                    break

            logger.info(f"Total unique decision links found: {len(decision_links)}")
            return list(decision_links)

        except Exception as e:
            logger.error(f"Error getting decision links: {e}")
            self.stats["errors"].append(f"Decision links error: {e!s}")
            return []

    def scrape_decision(self, url: str) -> Optional[dict]:
        """Scrape a single decision page"""
        try:
            self.driver.get(url)
            time.sleep(1)

            soup = BeautifulSoup(self.driver.page_source, "html.parser")

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

            self.stats["docs_found"] += 1

            return {
                "diary_number": diary_number,
                "title": title,
                "decision_date": decision_date,
                "category": category,
                "text": text_content,
                "url": url,
            }

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
        logger.info("Starting JK scraping operation with Selenium...")

        try:
            # Get all decision links
            all_decision_links = self.get_all_decision_links()

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

        finally:
            # Close browser
            self.driver.quit()

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
            "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/jk_scrape_results_selenium.json"
        )
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {output_file}")

        return self.stats


def main():
    scraper = JKSeleniumScraper()
    results = scraper.run()

    print("\n" + "=" * 60)
    print("JK SCRAPING RESULTS (SELENIUM)")
    print("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    main()
