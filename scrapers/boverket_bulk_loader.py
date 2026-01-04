#!/usr/bin/env python3
"""
Bulk loader for Boverket documents from URL list
Reads boverket_bulk_urls.txt and adds all documents to ChromaDB
"""

import sys
from pathlib import Path

# Add parent directory to path to import BoverketScraper
sys.path.insert(0, str(Path(__file__).parent))

from boverket_scraper import BoverketScraper


def load_urls_from_file(filepath: str):
    """Load URLs from text file"""
    documents = []

    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse line: URL|Title|Category|Year
            parts = line.split("|")
            if len(parts) < 4:
                print(f"⚠️  Skipping malformed line: {line}")
                continue

            url, title, category, year = parts
            documents.append(
                {
                    "url": url.strip(),
                    "title": title.strip(),
                    "metadata": {
                        "year": year.strip(),
                        "type": category.strip(),
                        "source_file": "bulk_urls.txt",
                    },
                }
            )

    return documents


def main():
    print("=" * 80)
    print("BOVERKET BULK LOADER")
    print("=" * 80)

    # Initialize scraper
    scraper = BoverketScraper()

    # Load URLs
    urls_file = Path(__file__).parent / "boverket_bulk_urls.txt"
    documents = load_urls_from_file(urls_file)

    print(f"Loaded {len(documents)} document URLs from {urls_file.name}")
    print("=" * 80)

    # Process each document
    for doc in documents:
        scraper.scrape_pdf_document(doc["url"], doc["title"], doc["metadata"])

    # Generate report
    scraper.generate_report()

    # Get total count from ChromaDB
    total_in_db = scraper.collection.count()
    print(f"\n📊 Total documents in ChromaDB: {total_in_db}")


if __name__ == "__main__":
    main()
