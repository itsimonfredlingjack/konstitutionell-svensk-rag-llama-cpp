#!/usr/bin/env python3
"""
RIKSBANKEN SCRAPER - SIMPLIFIED VERSION
Scrapes publications without embeddings (for speed)
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Constants
SOURCE_NAME = "riksbanken"
MIN_DOCS_THRESHOLD = 100

PUBLICATION_URLS = {
    "penningpolitisk_rapport": "https://www.riksbank.se/sv/penningpolitik/penningpolitisk-rapport/penningpolitiska-rapporter-och-uppdateringar/",
    "publikationer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/",
    "ekonomiska_kommentarer": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/ekonomiska-kommentarer/",
    "finansiell_stabilitet": "https://www.riksbank.se/sv/press-och-publicerat/publikationer/finansiell-stabilitetsrapport/",
}


class RiksbankenScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        self.docs_found = 0
        self.errors = []
        self.publications = []

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a web page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "lxml")
        except Exception as e:
            self.errors.append(f"Failed to fetch {url}: {e!s}")
            return None

    def extract_pdf_publication(self, pdf_link, pub_type: str) -> Optional[dict]:
        """Extract data from a PDF link"""
        try:
            pdf_url = pdf_link.get("href", "")
            if not pdf_url:
                return None

            if not pdf_url.startswith("http"):
                pdf_url = "https://www.riksbank.se" + pdf_url

            title = pdf_link.get_text(strip=True)
            if not title or len(title) < 5:
                parent = pdf_link.parent
                if parent:
                    title = parent.get_text(strip=True)[:200]

            # Extract date
            date_match = re.search(r"(202\d)-?(\d{2})", pdf_url + title)
            if date_match:
                date_str = f"{date_match.group(1)}-{date_match.group(2)}"
            else:
                date_match = re.search(r"(20\d{2})", pdf_url + title)
                date_str = date_match.group(1) if date_match else "Unknown"

            content = f"{title}\n\nDokumenttyp: {pub_type}\nFormat: PDF\nURL: {pdf_url}"

            return {
                "title": title or "Unnamed PDF",
                "url": pdf_url,
                "pub_type": pub_type,
                "date": date_str,
                "authors": "Riksbanken",
                "content": content,
                "source": SOURCE_NAME,
            }
        except Exception as e:
            self.errors.append(f"Error extracting PDF: {e!s}")
            return None

    def extract_html_publication(self, element, pub_type: str) -> Optional[dict]:
        """Extract data from HTML link"""
        try:
            link_elem = element.find("a", href=True) if element.name != "a" else element
            if not link_elem:
                return None

            url = link_elem["href"]
            if not url.startswith("http"):
                url = "https://www.riksbank.se" + url

            # Skip if it's just a category page
            if url.endswith("/publikationer/") or url.endswith("/rapporter/"):
                return None

            title = link_elem.get_text(strip=True)
            if not title or len(title) < 5:
                return None

            # Extract date
            date_match = re.search(r"(202\d)-?(\d{2})", url + title)
            if date_match:
                date_str = f"{date_match.group(1)}-{date_match.group(2)}"
            else:
                date_match = re.search(r"(20\d{2})", url + title)
                date_str = date_match.group(1) if date_match else "Unknown"

            content = f"{title}\n\nDokumenttyp: {pub_type}\nURL: {url}"

            return {
                "title": title,
                "url": url,
                "pub_type": pub_type,
                "date": date_str,
                "authors": "Riksbanken",
                "content": content,
                "source": SOURCE_NAME,
            }
        except Exception:
            return None

    def scrape_publication_list(self, pub_type: str, base_url: str) -> int:
        """Scrape a publication listing page"""
        print(f"\nScraping {pub_type} from {base_url}")
        soup = self.fetch_page(base_url)

        if not soup:
            return 0

        count = 0

        # Find PDF links
        pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
        print(f"  Found {len(pdf_links)} PDF links")

        for pdf_link in pdf_links:
            pub_data = self.extract_pdf_publication(pdf_link, pub_type)
            if pub_data:
                self.publications.append(pub_data)
                count += 1

        # Find HTML publication links
        html_links = soup.find_all("a", href=re.compile(r"/(publikationer|rapporter)/[^/]+/$"))
        print(f"  Found {len(html_links)} HTML publication links")

        seen_urls = set()
        for link in html_links:
            pub_data = self.extract_html_publication(link, pub_type)
            if pub_data and pub_data["url"] not in seen_urls:
                self.publications.append(pub_data)
                seen_urls.add(pub_data["url"])
                count += 1

        print(f"  Extracted {count} total documents")
        return count

    def run(self) -> dict:
        """Main scraping workflow"""
        print("=" * 60)
        print("RIKSBANKEN SCRAPER (SIMPLIFIED)")
        print("=" * 60)

        for pub_type, url in PUBLICATION_URLS.items():
            count = self.scrape_publication_list(pub_type, url)
            self.docs_found += count
            time.sleep(1)

        # Check threshold
        status = "OK"
        if self.docs_found < MIN_DOCS_THRESHOLD:
            status = "FLAGGAD"
            self.errors.append(
                f"SIMON: Riksbanken verkar ha problem - endast {self.docs_found} publikationer hittade"
            )

        result = {
            "myndighet": "Riksbanken",
            "status": status,
            "docs_found": self.docs_found,
            "docs_indexed": 0,  # Not indexed in this version
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
            "publications": self.publications[:10],  # Include first 10 as sample
        }

        return result


def main():
    scraper = RiksbankenScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("RESULTAT")
    print("=" * 60)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Save results
    output_file = f"/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/riksbanken_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {**result, "all_publications": scraper.publications}, f, indent=2, ensure_ascii=False
        )

    print(f"\nResults saved to: {output_file}")
    return result


if __name__ == "__main__":
    main()
