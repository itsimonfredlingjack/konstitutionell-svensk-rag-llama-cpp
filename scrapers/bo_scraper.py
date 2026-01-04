#!/usr/bin/env python3
"""
BO (Barnombudsmannen) Scraper
Samlar rapporter, remisser, årsredovisningar från barnombudsmannen.se
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


class BOScraper:
    def __init__(self):
        self.base_url = "https://www.barnombudsmannen.se"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Research Bot) - Constitutional AI Project"}
        )
        self.documents = []

    def scrape_all(self) -> list[dict]:
        """Scrape all document types from BO"""
        print(f"Starting BO scrape at {datetime.now()}")

        # Main sections to scrape (correct URLs)
        sections = [
            {
                "name": "Publikationer",
                "url": f"{self.base_url}/stallningstaganden/publikationer/",
                "doc_type": "publikation",
            },
            {
                "name": "Årsredovisningar",
                "url": f"{self.base_url}/om-oss/sa-har-styrs-verksamheten/arsredovisningar-och-budgetunderlag/",
                "doc_type": "årsredovisning",
            },
            {
                "name": "Årsrapporter",
                "url": f"{self.base_url}/om-oss/vart-uppdrag/arsrapporter/",
                "doc_type": "årsrapport",
            },
            {
                "name": "Remissvar och skrivelser",
                "url": f"{self.base_url}/stallningstaganden/remissvar-och-skrivelser/",
                "doc_type": "remiss",
            },
        ]

        for section in sections:
            try:
                print(f"\n=== Scraping {section['name']} ===")
                self.scrape_publication_section(section["url"], section["doc_type"])
                time.sleep(1)  # Be nice to the server
            except Exception as e:
                print(f"Error scraping {section['name']}: {e}")

        return self.documents

    def scrape_publication_section(self, url: str, doc_type: str):
        """Scrape a publication section (rapporter, remisser, etc)"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Find list items containing publications
            list_items = soup.find_all("li")

            publications_found = 0

            for li in list_items:
                try:
                    # Look for h4 heading (publication title)
                    h4 = li.find("h4")
                    if not h4:
                        continue

                    title = h4.get_text(strip=True)

                    # Get the main link (should wrap the h4)
                    main_link = li.find("a", href=True)
                    if not main_link:
                        continue

                    page_link = urljoin(self.base_url, main_link["href"])

                    # Look for metadata (year, category)
                    year = None
                    category = None
                    metadata_text = li.get_text()
                    year_match = re.search(r"\b20\d{2}\b", metadata_text)
                    if year_match:
                        year = year_match.group()

                    # Look for category labels
                    category_patterns = [
                        "Årsrapport",
                        "Övriga publikationer",
                        "Rapport",
                        "Remissvar",
                        "Skrivelse",
                        "Årsredovisning",
                    ]
                    for pattern in category_patterns:
                        if pattern.lower() in metadata_text.lower():
                            category = pattern
                            break

                    # Get description (paragraph after h4)
                    description = None
                    p = li.find("p")
                    if p:
                        description = p.get_text(strip=True)

                    # Look for PDF links
                    pdf_link = None
                    pdf_elem = li.find("a", href=re.compile(r"\.pdf$", re.I))
                    if pdf_elem:
                        pdf_link = urljoin(self.base_url, pdf_elem["href"])

                    # Create document
                    doc = self.create_document(
                        title=title,
                        url=pdf_link or page_link,
                        doc_type=category.lower() if category else doc_type,
                        date=year,
                        description=description or "",
                        page_url=page_link,
                    )
                    self.documents.append(doc)
                    publications_found += 1
                    print(f"  ✓ {title[:60]}...")

                except Exception:
                    # Silent skip for navigation items
                    continue

            print(f"Found {publications_found} publications on this page")

            # Check for pagination - look for next page link
            pagination = soup.find("nav", class_=re.compile(r"pag"))
            if pagination:
                next_link = pagination.find("a", string=re.compile(r"Nästa|Next|›|»"))
                if next_link and next_link.get("href"):
                    next_url = urljoin(self.base_url, next_link["href"])
                    print("  → Following pagination to next page")
                    time.sleep(1)
                    self.scrape_publication_section(next_url, doc_type)

        except Exception as e:
            print(f"Error fetching {url}: {e}")

    def create_document(
        self,
        title: str,
        url: str,
        doc_type: str,
        date: str = None,
        description: str = None,
        page_url: str = None,
    ) -> dict:
        """Create a standardized document dict"""

        # Generate doc_id
        doc_id = hashlib.sha256(url.encode()).hexdigest()[:16]

        # Extract year from date or URL
        year = None
        if date:
            year_match = re.search(r"20\d{2}", date)
            if year_match:
                year = year_match.group()
        if not year and url:
            year_match = re.search(r"20\d{2}", url)
            if year_match:
                year = year_match.group()

        return {
            "doc_id": doc_id,
            "title": title,
            "url": url,
            "page_url": page_url or url,
            "source": "barnombudsmannen",
            "source_full": "Barnombudsmannen",
            "doc_type": doc_type,
            "year": year,
            "date": date,
            "description": description or "",
            "scraped_at": datetime.now().isoformat(),
            "text_content": f"{title}\n\n{description or ''}",
        }


def main():
    scraper = BOScraper()
    documents = scraper.scrape_all()

    # Save to JSON
    output_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"bo_documents_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print("BO SCRAPE COMPLETE")
    print(f"{'='*60}")
    print(f"Total documents: {len(documents)}")
    print(f"Output file: {output_file}")

    # Count by type
    by_type = {}
    for doc in documents:
        dt = doc["doc_type"]
        by_type[dt] = by_type.get(dt, 0) + 1

    print("\nDocuments by type:")
    for dt, count in sorted(by_type.items()):
        print(f"  {dt}: {count}")

    return output_file


if __name__ == "__main__":
    output_file = main()
    print(f"\nJSON output: {output_file}")
