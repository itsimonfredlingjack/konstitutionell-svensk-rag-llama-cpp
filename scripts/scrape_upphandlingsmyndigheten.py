#!/usr/bin/env python3
"""
UPPHANDLINGSMYNDIGHETEN SCRAPER
================================
Scrape upphandlingsmyndigheten.se och lagra i ChromaDB.

Target: Vägledningar, rapporter, statistik, nyheter
Collection: swedish_gov_docs
Source: upphandlingsmyndigheten
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import chromadb
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class UpphandlingsmyndighetenScraper:
    def __init__(self, chromadb_path: str):
        self.base_url = "https://www.upphandlingsmyndigheten.se"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; SvenskaMyndighetenBot/1.0; +https://github.com/yourusername/swedish-gov-scraper)"
            }
        )

        # ChromaDB setup - egen collection för Upphandlingsmyndigheten
        self.client = chromadb.PersistentClient(path=chromadb_path)
        try:
            self.collection = self.client.get_or_create_collection(
                name="upphandlingsmyndigheten_docs",
                metadata={"description": "Upphandlingsmyndigheten dokument"},
            )
        except Exception as e:
            logger.error(f"ChromaDB collection error: {e}")
            raise

        self.scraped_urls: set[str] = set()
        self.documents_added = 0
        self.errors = []

    def generate_doc_id(self, url: str) -> str:
        """Generera unikt ID baserat på URL"""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def is_valid_url(self, url: str) -> bool:
        """Validera att URL är från upphandlingsmyndigheten.se"""
        parsed = urlparse(url)
        return parsed.netloc.endswith("upphandlingsmyndigheten.se")

    def extract_text_content(self, soup: BeautifulSoup) -> str:
        """Extrahera relevant text från sida"""
        # Ta bort script/style tags
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Prioritera main content
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile(r"content|main"))
        )

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        # Rensa överflödig whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = re.sub(r" +", " ", text)

        return text.strip()

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> dict:
        """Extrahera metadata från sida"""
        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else url

        # Hitta publiceringsdatum
        date_published = None
        date_meta = soup.find("meta", property="article:published_time")
        if date_meta:
            date_published = date_meta.get("content")

        # Kategori från URL
        category = "okategoriserad"
        if "/vagledning/" in url:
            category = "vägledning"
        elif "/rapport/" in url or "/statistik/" in url:
            category = "rapport"
        elif "/nyhet/" in url:
            category = "nyhet"
        elif "/om-oss/" in url:
            category = "om-myndigheten"

        return {
            "source": "upphandlingsmyndigheten",
            "url": url,
            "title": title_text,
            "category": category,
            "date_published": date_published or "unknown",
            "scraped_at": datetime.now().isoformat(),
        }

    def scrape_page(self, url: str) -> bool:
        """Scrape en enskild sida och lagra i ChromaDB"""
        if url in self.scraped_urls:
            return False

        if not self.is_valid_url(url):
            return False

        try:
            logger.info(f"Scraping: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Extrahera innehåll
            content = self.extract_text_content(soup)

            # Skip om för lite innehåll
            if len(content) < 200:
                logger.warning(f"Hoppar över {url} - för lite innehåll ({len(content)} tecken)")
                return False

            metadata = self.extract_metadata(soup, url)
            doc_id = self.generate_doc_id(url)

            # Lagra i ChromaDB
            self.collection.add(ids=[doc_id], documents=[content], metadatas=[metadata])

            self.scraped_urls.add(url)
            self.documents_added += 1

            logger.info(f"✓ Tillagd: {metadata['title'][:60]}... ({len(content)} tecken)")

            time.sleep(0.5)  # Rate limiting
            return True

        except requests.RequestException as e:
            error_msg = f"HTTP error för {url}: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
        except Exception as e:
            error_msg = f"Fel vid scraping av {url}: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False

    def discover_links(self, url: str) -> list[str]:
        """Hitta alla länkar på en sida"""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(url, href)

                if self.is_valid_url(full_url) and full_url not in self.scraped_urls:
                    links.append(full_url)

            return list(set(links))  # Deduplicate

        except Exception as e:
            logger.error(f"Fel vid länkdiscovery från {url}: {e}")
            return []

    def run(self, max_pages: int = 500):
        """Huvudloop - scrape webbplatsen"""
        logger.info("=" * 80)
        logger.info("UPPHANDLINGSMYNDIGHETEN SCRAPER STARTAR")
        logger.info("=" * 80)

        # Seed URLs - viktiga utgångspunkter
        seed_urls = [
            f"{self.base_url}/",
            f"{self.base_url}/vagledning/",
            f"{self.base_url}/statistik-och-analys/",
            f"{self.base_url}/nyheter/",
            f"{self.base_url}/om-upphandlingsmyndigheten/",
            f"{self.base_url}/upphandlingsregler/",
            f"{self.base_url}/innovationsupphandling/",
        ]

        # Bygg initial queue
        queue = []
        for seed_url in seed_urls:
            logger.info(f"Bygger queue från seed: {seed_url}")
            discovered = self.discover_links(seed_url)
            queue.extend(discovered)
            time.sleep(0.5)

        queue = list(set(queue))  # Deduplicate
        logger.info(f"Initialt {len(queue)} URLs i queue")

        # Scrape queue
        scraped_count = 0
        while queue and scraped_count < max_pages:
            url = queue.pop(0)

            if self.scrape_page(url):
                scraped_count += 1

                # Hitta fler länkar från den nya sidan
                if scraped_count % 10 == 0:  # Varje 10:e sida
                    new_links = self.discover_links(url)
                    for link in new_links:
                        if link not in queue and link not in self.scraped_urls:
                            queue.append(link)

                if scraped_count % 25 == 0:
                    logger.info(
                        f"Progress: {scraped_count} sidor scrapade, {len(queue)} kvar i queue"
                    )

        logger.info("=" * 80)
        logger.info("SCRAPING KLAR")
        logger.info("=" * 80)

    def get_stats(self) -> dict:
        """Returnera statistik från scraping"""
        return {
            "source": "upphandlingsmyndigheten",
            "documents_added": self.documents_added,
            "urls_scraped": len(self.scraped_urls),
            "errors": len(self.errors),
            "error_samples": self.errors[:5],  # Första 5 felen
            "timestamp": datetime.now().isoformat(),
        }


def main():
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

    scraper = UpphandlingsmyndighetenScraper(chromadb_path)
    scraper.run(max_pages=500)  # Scrape upp till 500 sidor

    stats = scraper.get_stats()

    # Spara stats till JSON
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/upphandlingsmyndigheten_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print("SLUTSTATISTIK")
    print("=" * 80)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"\nStats sparade till: {output_file}")

    # Flagga om <100 docs
    if stats["documents_added"] < 100:
        print("\n⚠️  VARNING: Färre än 100 dokument hittades!")
    else:
        print(f"\n✓ {stats['documents_added']} dokument tillagda till ChromaDB")


if __name__ == "__main__":
    main()
