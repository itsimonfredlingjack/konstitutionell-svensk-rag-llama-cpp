#!/usr/bin/env python3
"""
Trafikverket DiVA Portal Scraper
Scrapes publications from http://trafikverket.diva-portal.org
Stores results in ChromaDB collection: swedish_gov_docs
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.config import Settings
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Publication:
    """Represents a Trafikverket publication"""

    title: str
    url: str
    doc_id: str
    authors: list[str]
    year: str | None
    pub_type: str | None
    abstract: str | None
    pdf_url: str | None
    isbn: str | None
    issn: str | None
    source: str = "trafikverket"
    scraped_at: str = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def generate_hash(self) -> str:
        """Generate unique hash from URL"""
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


class TrafikverketScraper:
    """Scraper for Trafikverket DiVA Portal"""

    BASE_URL = "http://trafikverket.diva-portal.org"
    SEARCH_URL = f"{BASE_URL}/smash/resultList.jsf"

    def __init__(
        self,
        chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
    ):
        self.chromadb_path = chromadb_path
        self.publications: list[Publication] = []
        self.driver = None
        self.collection = None

    def setup_driver(self):
        """Setup Selenium Chrome driver"""
        logger.info("Setting up Chrome driver...")
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
        logger.info("Chrome driver ready")

    def setup_chromadb(self):
        """Setup ChromaDB connection"""
        logger.info(f"Connecting to ChromaDB at {self.chromadb_path}")
        client = chromadb.PersistentClient(
            path=self.chromadb_path, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = client.get_or_create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )
        logger.info(f"ChromaDB collection ready. Current count: {self.collection.count()}")

    def get_total_results(self) -> int | None:
        """Extract total number of results from search page"""
        try:
            # Try to find result count element
            # DiVA usually shows "Showing 1-20 of 5432" or similar
            result_text_elements = self.driver.find_elements(By.CLASS_NAME, "resultInfo")
            for element in result_text_elements:
                text = element.text
                if "of" in text.lower():
                    # Extract number after "of"
                    parts = text.split("of")
                    if len(parts) > 1:
                        number_str = parts[1].strip().split()[0].replace(",", "").replace(".", "")
                        return int(number_str)
        except Exception as e:
            logger.warning(f"Could not extract total results: {e}")
        return None

    def scrape_search_results(self, max_pages: int = 500):
        """Scrape all search results with pagination"""
        logger.info("Starting search results scraping...")

        # Start with simple search showing all results
        search_url = f"{self.SEARCH_URL}?searchType=SIMPLE&query=&noOfRows=50"
        self.driver.get(search_url)

        # Wait for results to load
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "resultRow"))
            )
        except TimeoutException:
            logger.error("Timeout waiting for search results")
            return

        # Get total results count
        total = self.get_total_results()
        if total:
            logger.info(f"Found {total} total publications in DiVA")

        page = 1
        while page <= max_pages:
            logger.info(f"Scraping page {page}...")

            # Extract publications from current page
            self.extract_publications_from_page()

            # Try to find and click next button
            try:
                next_buttons = self.driver.find_elements(By.LINK_TEXT, "Next")
                if not next_buttons:
                    next_buttons = self.driver.find_elements(By.PARTIAL_LINK_TEXT, "Nästa")

                if next_buttons and next_buttons[0].is_displayed():
                    next_buttons[0].click()
                    time.sleep(2)  # Wait for page load
                    page += 1
                else:
                    logger.info("No more pages found")
                    break
            except Exception as e:
                logger.info(f"Reached end of results at page {page}: {e}")
                break

        logger.info(f"Scraping complete. Total publications: {len(self.publications)}")

    def extract_publications_from_page(self):
        """Extract publication data from current page"""
        try:
            result_rows = self.driver.find_elements(By.CLASS_NAME, "resultRow")
            logger.info(f"Found {len(result_rows)} results on this page")

            for row in result_rows:
                try:
                    pub = self.extract_publication(row)
                    if pub:
                        self.publications.append(pub)
                except Exception as e:
                    logger.warning(f"Error extracting publication: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error extracting publications from page: {e}")

    def extract_publication(self, row_element) -> Publication | None:
        """Extract publication data from a result row"""
        try:
            # Title and URL
            title_elem = row_element.find_element(By.CLASS_NAME, "titleLink")
            title = title_elem.text.strip()
            url = title_elem.get_attribute("href")

            # Extract document ID from URL
            doc_id = url.split("pid=")[-1].split("&")[0] if "pid=" in url else ""

            # Authors
            authors = []
            try:
                author_elems = row_element.find_elements(By.CLASS_NAME, "author")
                authors = [a.text.strip() for a in author_elems if a.text.strip()]
            except NoSuchElementException:
                pass

            # Year
            year = None
            try:
                year_elem = row_element.find_element(By.CLASS_NAME, "year")
                year = year_elem.text.strip()
            except NoSuchElementException:
                pass

            # Publication type
            pub_type = None
            try:
                type_elem = row_element.find_element(By.CLASS_NAME, "pubType")
                pub_type = type_elem.text.strip()
            except NoSuchElementException:
                pass

            # Abstract (if visible)
            abstract = None
            try:
                abstract_elem = row_element.find_element(By.CLASS_NAME, "abstract")
                abstract = abstract_elem.text.strip()
            except NoSuchElementException:
                pass

            # PDF URL
            pdf_url = None
            try:
                pdf_links = row_element.find_elements(By.PARTIAL_LINK_TEXT, "Full text")
                if pdf_links:
                    pdf_url = pdf_links[0].get_attribute("href")
            except NoSuchElementException:
                pass

            return Publication(
                title=title,
                url=url,
                doc_id=doc_id,
                authors=authors,
                year=year,
                pub_type=pub_type,
                abstract=abstract,
                pdf_url=pdf_url,
                isbn=None,
                issn=None,
            )

        except Exception as e:
            logger.warning(f"Error parsing publication row: {e}")
            return None

    def save_to_chromadb(self):
        """Save publications to ChromaDB"""
        logger.info(f"Saving {len(self.publications)} publications to ChromaDB...")

        if not self.collection:
            self.setup_chromadb()

        for pub in self.publications:
            try:
                doc_hash = pub.generate_hash()

                # Create searchable text
                text_parts = [pub.title]
                if pub.abstract:
                    text_parts.append(pub.abstract)
                if pub.authors:
                    text_parts.append(" ".join(pub.authors))

                document_text = "\n".join(text_parts)

                # Prepare metadata
                metadata = {
                    "source": pub.source,
                    "url": pub.url,
                    "title": pub.title[:500],  # ChromaDB has length limits
                    "year": pub.year or "unknown",
                    "pub_type": pub.pub_type or "unknown",
                    "doc_id": pub.doc_id,
                    "scraped_at": pub.scraped_at,
                }

                if pub.pdf_url:
                    metadata["pdf_url"] = pub.pdf_url

                # Add to collection
                self.collection.add(ids=[doc_hash], documents=[document_text], metadatas=[metadata])

            except Exception as e:
                logger.warning(f"Error adding publication to ChromaDB: {e}")
                continue

        logger.info("ChromaDB indexing complete")

    def save_json_report(self) -> str:
        """Save JSON report of scraping results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"trafikverket_scrape_{timestamp}.json"

        report = {
            "source": "trafikverket",
            "scraped_at": datetime.now().isoformat(),
            "total_publications": len(self.publications),
            "chromadb_collection": "swedish_gov_docs",
            "chromadb_path": self.chromadb_path,
            "publications": [pub.to_dict() for pub in self.publications],
            "status": "WARNING: Less than 100 documents"
            if len(self.publications) < 100
            else "SUCCESS",
        }

        report_path = Path(__file__).parent / report_file
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Report saved to {report_path}")
        return str(report_path)

    def run(self):
        """Execute full scraping workflow"""
        try:
            logger.info("=== TRAFIKVERKET SCRAPER START ===")

            self.setup_driver()
            self.setup_chromadb()

            # Scrape all publications
            self.scrape_search_results()

            # Save to ChromaDB
            if self.publications:
                self.save_to_chromadb()

            # Generate report
            report_path = self.save_json_report()

            # Flag if too few documents
            if len(self.publications) < 100:
                logger.warning(
                    f"⚠️  WARNING: Only found {len(self.publications)} documents (expected 100+)"
                )

            logger.info("=== TRAFIKVERKET SCRAPER COMPLETE ===")
            logger.info(f"Total documents scraped: {len(self.publications)}")
            logger.info(f"Report: {report_path}")

            return report_path

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Browser closed")


def main():
    scraper = TrafikverketScraper()
    scraper.run()


if __name__ == "__main__":
    main()
