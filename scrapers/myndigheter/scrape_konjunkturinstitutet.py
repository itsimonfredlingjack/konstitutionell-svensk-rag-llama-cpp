#!/usr/bin/env python3
"""
Konjunkturinstitutet Scraper
============================
Scrapes publications from konj.se - Swedish National Institute of Economic Research.
Publications organized by category: konjunkturlaget, remissvar, lonbildningsrapporten, etc.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "konjunkturinstitutet"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.konj.se"

HEADERS = {"User-Agent": "KonjunkturBot/1.0 (Constitutional AI Research, respekterar robots.txt)"}

# Publication categories
PUBLICATION_PAGES = [
    ("konjunkturlaget", f"{BASE_URL}/publikationer/konjunkturlaget.html"),
    ("remissvar", f"{BASE_URL}/publikationer/remissvar.html"),
    ("lonbildningsrapporten", f"{BASE_URL}/publikationer/lonbildningsrapporten.html"),
    ("ovriga-publikationer", f"{BASE_URL}/publikationer/ovriga-publikationer.html"),
    ("specialstudier", f"{BASE_URL}/publikationer/specialstudier.html"),
    ("working-papers", f"{BASE_URL}/publikationer/working-papers.html"),
]

DELAY_BETWEEN_REQUESTS = 2.0


@dataclass
class Document:
    """A scraped document."""

    url: str
    title: str
    category: str
    year: Optional[str]
    filename: str
    filepath: str
    sha256: str
    size_bytes: int
    scraped_at: str


def extract_year(url: str, title: str) -> Optional[str]:
    """Extract year from URL or title."""
    # Try title first (e.g., "september 2025", "mars 2024")
    match = re.search(r"(20\d{2})", title)
    if match:
        return match.group(1)

    # Try URL
    match = re.search(r"(20\d{2})", url)
    if match:
        return match.group(1)

    return None


def get_pdf_links(session: requests.Session) -> list[dict]:
    """Get all PDF links from all publication pages."""
    all_pdfs = []
    seen_urls = set()

    for category, url in PUBLICATION_PAGES:
        logger.info(f"Fetching {category}: {url}")

        try:
            time.sleep(1)  # Be nice
            resp = session.get(url, headers=HEADERS, timeout=30)

            if resp.status_code != 200:
                logger.warning(f"  Status {resp.status_code} for {url}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all PDF links
            pdf_links = soup.find_all("a", href=re.compile(r"\.pdf$", re.I))
            category_count = 0

            for link in pdf_links:
                href = link.get("href", "")
                full_url = urljoin(url, href)

                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # Get link text as title
                title = link.get_text(strip=True)
                if not title:
                    title = Path(urlparse(full_url).path).stem.replace("-", " ")

                year = extract_year(full_url, title)

                all_pdfs.append(
                    {"url": full_url, "title": title[:200], "category": category, "year": year}
                )
                category_count += 1

            logger.info(f"  Found {category_count} PDFs")

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")

    logger.info(f"Total unique PDFs found: {len(all_pdfs)}")
    return all_pdfs


def download_pdf(session: requests.Session, url: str, category: str) -> Optional[dict]:
    """Download a PDF and return metadata."""
    try:
        time.sleep(DELAY_BETWEEN_REQUESTS)

        resp = session.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()

        content = resp.content
        sha256 = hashlib.sha256(content).hexdigest()

        # Create category directory
        cat_dir = PDF_CACHE_DIR / category
        cat_dir.mkdir(exist_ok=True)

        # Generate filename
        original_name = Path(urlparse(url).path).name
        filename = f"{sha256[:8]}_{original_name}"
        filepath = cat_dir / filename

        # Skip if already exists
        if filepath.exists():
            logger.debug(f"Already exists: {filename}")
            return None

        filepath.write_bytes(content)
        logger.info(f"Downloaded: {filename} ({len(content):,} bytes)")

        return {
            "filepath": str(filepath),
            "filename": filename,
            "sha256": sha256,
            "size_bytes": len(content),
        }

    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def scrape_konjunkturinstitutet(max_downloads: int = None) -> dict:
    """Main scraping function."""
    start_time = time.time()

    session = requests.Session()

    # Get all PDF links
    pdf_links = get_pdf_links(session)

    # Download PDFs
    documents = []
    errors = []

    total_to_download = (
        len(pdf_links) if max_downloads is None else min(len(pdf_links), max_downloads)
    )

    for i, pdf_info in enumerate(pdf_links[:total_to_download]):
        logger.info(f"[{i+1}/{total_to_download}] {pdf_info['title'][:50]}...")

        result = download_pdf(session, pdf_info["url"], pdf_info["category"])

        if result:
            doc = Document(
                url=pdf_info["url"],
                title=pdf_info["title"],
                category=pdf_info["category"],
                year=pdf_info["year"],
                filename=result["filename"],
                filepath=result["filepath"],
                sha256=result["sha256"],
                size_bytes=result["size_bytes"],
                scraped_at=datetime.now().isoformat(),
            )
            documents.append(doc)
        else:
            errors.append(pdf_info["url"])

    elapsed = time.time() - start_time

    # Summary
    total_bytes = sum(d.size_bytes for d in documents)

    from collections import Counter

    cat_counts = Counter(d.category for d in documents)
    year_counts = Counter(d.year for d in documents if d.year)

    result = {
        "source": "Konjunkturinstitutet",
        "url": BASE_URL,
        "scraped_at": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "total_found": len(pdf_links),
        "total_downloaded": len(documents),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "by_category": dict(cat_counts),
        "by_year": dict(sorted(year_counts.items(), reverse=True)),
        "errors": len(errors),
        "documents": [asdict(d) for d in documents],
    }

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Konjunkturinstitutet publications")
    parser.add_argument("--max", "-m", type=int, help="Max documents to download")
    parser.add_argument(
        "--output", "-o", default="konjunkturinstitutet_report.json", help="Output file"
    )

    args = parser.parse_args()

    result = scrape_konjunkturinstitutet(max_downloads=args.max)

    # Print summary
    print("\n" + "=" * 60)
    print("KONJUNKTURINSTITUTET SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Found: {result['total_found']} PDFs")
    print(f"Downloaded: {result['total_downloaded']} PDFs")
    print(f"Total size: {result['total_mb']} MB")
    print(f"Time: {result['elapsed_seconds']} seconds")
    print("\nBy category:")
    for cat, count in result["by_category"].items():
        print(f"  {cat}: {count}")
    print("\nBy year (top 5):")
    for year, count in list(result["by_year"].items())[:5]:
        print(f"  {year}: {count}")
    print(f"\nErrors: {result['errors']}")

    # Save report
    output_file = BASE_DIR / args.output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to: {output_file}")
