#!/usr/bin/env python3
"""
BO (Barnombudsmannen) Scraper v2
Direct approach: Find all PDFs and publication pages
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class BOScraperV2:
    def __init__(self):
        self.base_url = "https://www.barnombudsmannen.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Research Bot) - Constitutional AI Project"}
        )
        self.documents = []
        self.seen_urls: set[str] = set()

    def scrape_all(self) -> list[dict]:
        """Scrape all publications from BO"""
        print(f"Starting BO scrape v2 at {datetime.now()}")

        # Start URLs - publication listing pages and specific publication pages
        start_urls = [
            # Main publication page
            f"{self.base_url}/stallningstaganden/publikationer/",
            # Specific publication categories from the main page
            f"{self.base_url}/stallningstaganden/publikationer/?filter=Årsrapport",
            f"{self.base_url}/stallningstaganden/publikationer/?filter=Rapport",
            f"{self.base_url}/stallningstaganden/publikationer/?filter=Övriga+publikationer",
            # Annual reports
            f"{self.base_url}/om-oss/vart-uppdrag/arsrapporter/",
            # Remissvar och skrivelser - main page
            f"{self.base_url}/stallningstaganden/remissvar-och-skrivelser/",
            # Annual reports and documents under "Om oss"
            f"{self.base_url}/om-oss/sa-har-styrs-verksamheten/arsredovisningar-och-budgetunderlag/",
        ]

        for url in start_urls:
            print(f"\n=== Scraping {url} ===")
            self.scrape_publication_list(url)
            time.sleep(1)

        return self.documents

    def scrape_publication_list(self, url: str, page_num: int = 1):
        """Scrape a publication listing page with pagination"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Find all links on the page
            all_links = soup.find_all("a", href=True)

            publications_found = 0

            for link in all_links:
                href = link["href"]
                full_url = urljoin(self.base_url, href)

                # Skip if we've seen this URL
                if full_url in self.seen_urls:
                    continue

                # Check if this looks like a publication
                if self.is_publication_link(link, href, full_url):
                    self.seen_urls.add(full_url)

                    # Extract publication info
                    title = self.extract_title(link, soup)

                    if title and len(title) > 15:  # Skip short navigation titles
                        doc = self.extract_publication_details(link, full_url, title, soup)
                        if doc:
                            self.documents.append(doc)
                            publications_found += 1
                            print(f"  ✓ {title[:60]}...")

            print(f"Page {page_num}: Found {publications_found} publications")

            # Check for next page
            next_page = self.find_next_page(soup, url)
            if next_page and page_num < 20:  # Max 20 pages
                print(f"  → Following to page {page_num + 1}")
                time.sleep(1)
                self.scrape_publication_list(next_page, page_num + 1)

        except Exception as e:
            print(f"Error scraping {url}: {e}")

    def is_publication_link(self, link, href: str, full_url: str) -> bool:
        """Determine if a link points to a publication"""

        # Direct PDF link
        if href.lower().endswith(".pdf"):
            return True

        # Link to /aktuellt/ (news/reports)
        if "/aktuellt/" in href and not href.endswith("/aktuellt/"):
            return True

        # Link to /stallningstaganden/publikationer/ with specific publication
        if "/stallningstaganden/publikationer/" in href:
            # Must have something after publikationer/
            if href.count("/") > href.count("/stallningstaganden/publikationer/"):
                return True

        # Link to /stallningstaganden/remissvar-och-skrivelser/ with specific item
        if "/stallningstaganden/remissvar-och-skrivelser/" in href:
            if href.count("/") > href.count("/stallningstaganden/remissvar-och-skrivelser/"):
                return True

        # Parent contains publication indicators
        parent = link.find_parent(["li", "article", "div"])
        if parent:
            parent_text = parent.get_text().lower()
            # Has year indicator (2020-2029)
            if re.search(r"20[12]\d", parent_text):
                # Has category indicator
                if any(
                    cat in parent_text
                    for cat in ["rapport", "årsrapport", "publikation", "remiss", "skrivelse"]
                ):
                    return True

        return False

    def extract_title(self, link, soup) -> str:
        """Extract publication title"""

        # Title from link text
        title = link.get_text(strip=True)

        if not title or len(title) < 10:
            # Try to find nearby heading
            parent = link.find_parent(["li", "article", "div"])
            if parent:
                h4 = parent.find("h4")
                if h4:
                    title = h4.get_text(strip=True)
                else:
                    h3 = parent.find("h3")
                    if h3:
                        title = h3.get_text(strip=True)

        return title

    def extract_publication_details(self, link, url: str, title: str, soup) -> dict:
        """Extract detailed publication information"""

        # Determine doc_type
        doc_type = "publikation"
        parent = link.find_parent(["li", "article", "div"])

        if parent:
            parent_text = parent.get_text().lower()

            if "årsrapport" in parent_text:
                doc_type = "årsrapport"
            elif "årsredovisning" in parent_text:
                doc_type = "årsredovisning"
            elif "remissvar" in parent_text or "remiss" in parent_text:
                doc_type = "remiss"
            elif "skrivelse" in parent_text:
                doc_type = "skrivelse"
            elif "rapport" in parent_text:
                doc_type = "rapport"

        # Extract year
        year = None
        if parent:
            year_match = re.search(r"\b(20[12]\d)\b", parent.get_text())
            if year_match:
                year = year_match.group(1)

        if not year and url:
            year_match = re.search(r"20[12]\d", url)
            if year_match:
                year = year_match.group()

        # Extract description
        description = ""
        if parent:
            p = parent.find("p")
            if p:
                description = p.get_text(strip=True)

        # Generate doc_id
        doc_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        return {
            "doc_id": doc_id,
            "title": title,
            "url": url,
            "page_url": url,
            "source": "barnombudsmannen",
            "source_full": "Barnombudsmannen",
            "doc_type": doc_type,
            "year": year,
            "date": year,
            "description": description,
            "scraped_at": datetime.now().isoformat(),
            "text_content": f"{title}\n\n{description}",
        }

    def find_next_page(self, soup, current_url: str) -> str:
        """Find next page link in pagination"""

        # Look for explicit next page links
        all_links = soup.find_all("a", href=True)

        for link in all_links:
            link_text = link.get_text(strip=True).lower()

            # Direct next page indicators
            if link_text in [
                "nästa",
                "next",
                "›",
                "»",
                "sida2",
                "sida3",
                "sida4",
                "sida5",
                "sida6",
                "sida7",
                "sida8",
                "sida9",
                "sida10",
            ]:
                # Don't follow if it's "Gå till sista sidan"
                if "sista" not in link_text:
                    href = link["href"]
                    # Make sure it's not already visited
                    full_url = urljoin(self.base_url, href)
                    if full_url != current_url and full_url not in self.seen_urls:
                        # Check if it's a pagination link (not a different section)
                        if "sida" in href or "?page=" in href or "/page/" in href:
                            return full_url

        # Look for numbered pagination (sida2, sida3, etc.)
        # Extract current page from URL
        current_page_num = 1
        if "sida" in current_url:
            match = re.search(r"sida(\d+)", current_url)
            if match:
                current_page_num = int(match.group(1))

        # Look for next page number
        next_page_text = f"sida{current_page_num + 1}"
        for link in all_links:
            if next_page_text in link.get("href", ""):
                return urljoin(self.base_url, link["href"])

        return None


def main():
    scraper = BOScraperV2()
    documents = scraper.scrape_all()

    # Deduplicate
    unique_docs = {}
    for doc in documents:
        doc_id = doc["doc_id"]
        if doc_id not in unique_docs:
            unique_docs[doc_id] = doc

    unique_list = list(unique_docs.values())

    # Save to JSON
    output_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"bo_documents_v2_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(unique_list, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("BO SCRAPE V2 COMPLETE")
    print(f"{'='*60}")
    print(f"Total documents found: {len(documents)}")
    print(f"Unique documents: {len(unique_list)}")
    print(f"Duplicates removed: {len(documents) - len(unique_list)}")
    print(f"Output file: {output_file}")

    # Count by type
    by_type = {}
    for doc in unique_list:
        dt = doc["doc_type"]
        by_type[dt] = by_type.get(dt, 0) + 1

    print("\nDocuments by type:")
    for dt, count in sorted(by_type.items()):
        print(f"  {dt}: {count}")

    # Count by year
    by_year = {}
    for doc in unique_list:
        year = doc.get("year", "unknown")
        by_year[year] = by_year.get(year, 0) + 1

    print("\nDocuments by year:")
    # Filter out None values and sort
    year_counts = [(y if y else "unknown", c) for y, c in by_year.items()]
    for year, count in sorted(year_counts, key=lambda x: (x[0] == "unknown", x[0]), reverse=True):
        print(f"  {year}: {count}")

    return output_file


if __name__ == "__main__":
    output_file = main()
    print(f"\nJSON output: {output_file}")
