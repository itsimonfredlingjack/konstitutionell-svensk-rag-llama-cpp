#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - STATSKONTORET
Scrape utredningar, rapporter, publikationer från statskontoret.se
Requires Selenium for JavaScript-rendered content
"""

import hashlib
import json
import re
import time
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class StatskontoretScraper:
    def __init__(self):
        self.base_url = "https://www.statskontoret.se"
        self.documents: list[dict] = []
        self.seen_urls: set[str] = set()

        # Setup headless Chrome
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        self.driver = webdriver.Chrome(options=chrome_options)

    def get_text_hash(self, text: str) -> str:
        """Generate unique ID from content"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def scrape_publications_list(self, url: str) -> list[str]:
        """Scrape list of publication URLs using Selenium"""
        try:
            self.driver.get(url)

            # Wait for publications to load
            wait = WebDriverWait(self.driver, 20)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/publicerat/']")))

            # Scroll to load lazy content
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            while True:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # Get page source and parse
            soup = BeautifulSoup(self.driver.page_source, "html.parser")

            links = []
            # Find all publication links
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(url, href)

                # Look for publication detail pages
                if "/publicerat/" in href and full_url not in self.seen_urls:
                    # Avoid filters and category pages
                    if "?" not in href and href.count("/") > 2:
                        links.append(full_url)
                        self.seen_urls.add(full_url)

            return links
        except Exception as e:
            print(f"Error scraping list {url}: {e}")
            return []

    def scrape_publication_page(self, url: str) -> dict | None:
        """Scrape individual publication page using Selenium"""
        try:
            self.driver.get(url)
            time.sleep(3)  # Wait for content to load
            soup = BeautifulSoup(self.driver.page_source, "html.parser")

            # Extract title
            title = None
            for selector in ["h1", "h2", ".publication-title", ".report-title"]:
                el = soup.select_one(selector)
                if el:
                    title = el.get_text(strip=True)
                    break

            if not title:
                title = soup.title.string if soup.title else "Untitled"

            # Extract main content
            content_parts = []

            # Try different content selectors
            for selector in [
                "main",
                "article",
                ".content",
                ".publication-content",
                ".report-content",
                "#main-content",
            ]:
                content = soup.select_one(selector)
                if content:
                    # Remove scripts, styles, nav
                    for tag in content.find_all(["script", "style", "nav", "aside"]):
                        tag.decompose()
                    content_parts.append(content.get_text(separator="\n", strip=True))
                    break

            # If no main content found, get all paragraphs
            if not content_parts:
                paragraphs = soup.find_all("p")
                content_parts = [
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                ]

            full_text = "\n\n".join(content_parts)

            # Extract metadata
            metadata = {"url": url, "title": title, "scraped_at": datetime.now().isoformat()}

            # Look for publication date
            page_text = self.driver.page_source
            for pattern in [
                r"publicerad[:\s]+(\d{4}-\d{2}-\d{2})",
                r"utkom[:\s]+(\d{4})",
                r"(\d{4}-\d{2}-\d{2})",
            ]:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    metadata["published"] = match.group(1)
                    break

            # Look for PDF link
            pdf_link = soup.find("a", href=re.compile(r"\.pdf$", re.I))
            if pdf_link:
                metadata["pdf_url"] = urljoin(url, pdf_link["href"])

            # Only save if we have meaningful content
            if len(full_text) > 200:
                return {"id": self.get_text_hash(url), "text": full_text, "metadata": metadata}

            return None

        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None

    def run_sweep(self) -> dict:
        """Execute full sweep of Statskontoret"""
        start_time = time.time()

        print("🔍 Starting Statskontoret sweep...")

        try:
            # Start point - main publications page
            entry_point = f"{self.base_url}/publicerat/"

            print(f"  Loading {entry_point}...")
            pub_urls = self.scrape_publications_list(entry_point)

            print(f"  Found {len(pub_urls)} publication URLs")

            # Scrape each publication
            for i, url in enumerate(pub_urls, 1):
                print(f"  [{i}/{len(pub_urls)}] Scraping {url}")
                doc = self.scrape_publication_page(url)
                if doc:
                    self.documents.append(doc)
                time.sleep(1)  # Rate limiting

        finally:
            # Clean up Selenium driver
            self.driver.quit()

        duration = time.time() - start_time

        # Prepare result
        result = {
            "source": "statskontoret",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": round(duration, 2),
            "documents_scraped": len(self.documents),
            "urls_checked": len(pub_urls),
            "documents": self.documents,
            "chromadb_ready": True,  # Format ready for ChromaDB
        }

        return result


def main():
    scraper = StatskontoretScraper()
    result = scraper.run_sweep()

    # Save to JSON
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/statskontoret_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\n✅ Sweep complete!")
    print(f"   Documents: {result['documents_scraped']}")
    print(f"   Duration: {result['duration_seconds']}s")
    print(f"   Output: {output_file}")

    return result


if __name__ == "__main__":
    main()
