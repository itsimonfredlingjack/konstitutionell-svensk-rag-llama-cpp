#!/usr/bin/env python3
"""
Statskontoret Scraper
=====================
Scrapes reports from statskontoret.se - Swedish Agency for Public Management.
Reports are organized by year, with PDFs on individual report pages.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Configuration
BASE_DIR = Path(__file__).parent
PDF_CACHE_DIR = BASE_DIR / "pdf_cache" / "statskontoret"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.statskontoret.se"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

HEADERS = {
    "User-Agent": "StatskontoretBot/1.0 (Constitutional AI Research, respekterar robots.txt)"
}

DELAY_BETWEEN_REQUESTS = 2.0


@dataclass
class Document:
    """A scraped document."""

    url: str
    title: str
    report_page: str
    year: str
    filename: str
    filepath: str
    sha256: str
    size_bytes: int
    scraped_at: str


def get_all_report_links(session: requests.Session) -> list[dict]:
    """Get all report links from sitemap.xml."""
    logger.info(f"Fetching sitemap from: {SITEMAP_URL}")

    try:
        resp = session.get(SITEMAP_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "xml")

        reports = []
        seen = set()

        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            if not loc:
                continue

            url = loc.text.strip()

            # Match report pages pattern: /uppdrag-och-rapporter/rapporter/YYYY/slug/
            match = re.search(r"/uppdrag-och-rapporter/rapporter/(20\d{2})/([^/]+)/?$", url)
            if match and url not in seen:
                seen.add(url)
                year = match.group(1)
                slug = match.group(2)

                # Convert slug to title (replace dashes with spaces, capitalize)
                title = slug.replace("-", " ").replace("/", "").title()

                reports.append({"report_page": url, "title": title[:200], "year": year})

        logger.info(f"Found {len(reports)} reports in sitemap")
        return reports

    except Exception as e:
        logger.error(f"Error fetching sitemap: {e}")
        return []


def get_pdf_from_report_page(session: requests.Session, report_url: str) -> str | None:
    """Get PDF URL from a report page."""
    try:
        time.sleep(DELAY_BETWEEN_REQUESTS)
        resp = session.get(report_url, headers=HEADERS, timeout=30)

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Find PDF link (usually in contentassets or globalassets)
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if ".pdf" in href.lower():
                return urljoin(report_url, href)

        return None

    except Exception as e:
        logger.debug(f"Error getting PDF from {report_url}: {e}")
        return None


def download_pdf(session: requests.Session, url: str, year: str) -> dict | None:
    """Download a PDF and return metadata."""
    try:
        time.sleep(DELAY_BETWEEN_REQUESTS)

        # Clean URL (remove query params for cleaner filenames)
        clean_url = url.split("?")[0]

        resp = session.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()

        content = resp.content
        sha256 = hashlib.sha256(content).hexdigest()

        # Create year directory
        year_dir = PDF_CACHE_DIR / year
        year_dir.mkdir(exist_ok=True)

        # Generate filename
        original_name = Path(urlparse(clean_url).path).name
        filename = f"{sha256[:8]}_{original_name}"
        filepath = year_dir / filename

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


def scrape_statskontoret(max_downloads: int = None, years: list[int] = None) -> dict:
    """Main scraping function."""
    start_time = time.time()

    session = requests.Session()

    # Phase 1: Get all report pages from main page
    all_reports = get_all_report_links(session)

    # Filter by years if specified
    if years:
        all_reports = [r for r in all_reports if int(r["year"]) in years]

    logger.info(f"Total report pages found: {len(all_reports)}")

    # Phase 2: Get PDF URLs from each report page
    # If max_downloads is set, limit discovery to avoid checking all 1300+ pages
    if max_downloads:
        # Check at most 2x max_downloads pages (some might not have PDFs)
        discovery_limit = min(len(all_reports), max_downloads * 2)
        logger.info(
            f"Limiting discovery to {discovery_limit} pages (max_downloads={max_downloads})"
        )
    else:
        discovery_limit = len(all_reports)

    pdf_infos = []
    for i, report in enumerate(all_reports[:discovery_limit]):
        logger.info(f"[{i + 1}/{discovery_limit}] Getting PDF from: {report['title'][:40]}...")
        pdf_url = get_pdf_from_report_page(session, report["report_page"])

        if pdf_url:
            pdf_infos.append({**report, "pdf_url": pdf_url})
        else:
            logger.warning(f"  No PDF found for: {report['title'][:40]}")

        # Early exit if we have enough PDFs
        if max_downloads and len(pdf_infos) >= max_downloads:
            logger.info(f"Found enough PDFs ({len(pdf_infos)}), stopping discovery")
            break

    logger.info(f"PDFs found: {len(pdf_infos)}")

    # Phase 3: Download PDFs
    documents = []
    errors = []

    total_to_download = (
        len(pdf_infos) if max_downloads is None else min(len(pdf_infos), max_downloads)
    )

    for i, pdf_info in enumerate(pdf_infos[:total_to_download]):
        logger.info(f"[{i + 1}/{total_to_download}] Downloading: {pdf_info['title'][:40]}...")

        result = download_pdf(session, pdf_info["pdf_url"], pdf_info["year"])

        if result:
            doc = Document(
                url=pdf_info["pdf_url"],
                title=pdf_info["title"],
                report_page=pdf_info["report_page"],
                year=pdf_info["year"],
                filename=result["filename"],
                filepath=result["filepath"],
                sha256=result["sha256"],
                size_bytes=result["size_bytes"],
                scraped_at=datetime.now().isoformat(),
            )
            documents.append(doc)
        else:
            errors.append(pdf_info["pdf_url"])

    elapsed = time.time() - start_time

    # Summary
    total_bytes = sum(d.size_bytes for d in documents)

    from collections import Counter

    year_counts = Counter(d.year for d in documents)

    result = {
        "source": "Statskontoret",
        "url": BASE_URL,
        "scraped_at": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "total_report_pages": len(all_reports),
        "total_pdfs_found": len(pdf_infos),
        "total_downloaded": len(documents),
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "by_year": dict(sorted(year_counts.items(), reverse=True)),
        "errors": len(errors),
        "documents": [asdict(d) for d in documents],
    }

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Statskontoret publications")
    parser.add_argument("--max", "-m", type=int, help="Max documents to download")
    parser.add_argument(
        "--years", "-y", nargs="+", type=int, help="Years to scrape (e.g., 2023 2024 2025)"
    )
    parser.add_argument("--output", "-o", default="statskontoret_report.json", help="Output file")

    args = parser.parse_args()

    result = scrape_statskontoret(max_downloads=args.max, years=args.years)

    # Print summary
    print("\n" + "=" * 60)
    print("STATSKONTORET SCRAPING COMPLETE")
    print("=" * 60)
    print(f"Report pages found: {result['total_report_pages']}")
    print(f"PDFs found: {result['total_pdfs_found']}")
    print(f"Downloaded: {result['total_downloaded']} PDFs")
    print(f"Total size: {result['total_mb']} MB")
    print(f"Time: {result['elapsed_seconds']} seconds")
    print("\nBy year:")
    for year, count in result["by_year"].items():
        print(f"  {year}: {count}")
    print(f"\nErrors: {result['errors']}")

    # Save report
    output_file = BASE_DIR / args.output
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to: {output_file}")
