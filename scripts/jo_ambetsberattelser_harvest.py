#!/usr/bin/env python3
"""
JO Ämbetsberättelser Harvester
Hämtar alla årsberättelser från JO (1971-2024)
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    import fitz  # PyMuPDF

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    print("WARNING: PyMuPDF not installed - PDF text extraction disabled")

OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
PDF_DIR = OUTPUT_DIR / "jo_pdfs"


def fetch_ambetsberattelser_page():
    """Fetch the JO ämbetsberättelser page."""
    url = "https://www.jo.se/om-jo/ambetsberattelser/"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print(f"Fetching: {url}")
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def extract_pdf_links(html_content):
    """Extract PDF links from the page."""
    soup = BeautifulSoup(html_content, "html.parser")

    pdf_links = []

    # Look for links to data.riksdagen.se/fil/
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        # Riksdagen PDF links
        if "data.riksdagen.se/fil/" in href:
            title = link.get_text(strip=True) or href.split("/")[-1]
            pdf_links.append({"url": href, "title": title, "source": "riksdagen"})

        # Direct PDF links on jo.se
        elif href.endswith(".pdf"):
            if not href.startswith("http"):
                href = (
                    f"https://www.jo.se{href}"
                    if href.startswith("/")
                    else f"https://www.jo.se/{href}"
                )
            title = link.get_text(strip=True) or href.split("/")[-1]
            pdf_links.append({"url": href, "title": title, "source": "jo.se"})

    # Deduplicate
    seen = set()
    unique_links = []
    for link in pdf_links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)

    return unique_links


def download_pdf(url, output_path):
    """Download a PDF file."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
    }

    response = requests.get(url, headers=headers, timeout=60, stream=True)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    return output_path


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyMuPDF."""
    if not HAS_PYMUPDF:
        return None

    try:
        doc = fitz.open(pdf_path)
        text_parts = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

        doc.close()
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"  Error extracting text: {e}")
        return None


def extract_year_from_title(title):
    """Try to extract year from title."""
    # Look for 4-digit year
    match = re.search(r"(19[7-9]\d|20[0-2]\d)", title)
    if match:
        return match.group(1)
    return None


def main():
    print("=" * 70)
    print("JO ÄMBETSBERÄTTELSER HARVESTER")
    print("=" * 70)

    # Create directories
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch page
    try:
        html = fetch_ambetsberattelser_page()
    except Exception as e:
        print(f"ERROR fetching page: {e}")
        return

    # Extract PDF links
    pdf_links = extract_pdf_links(html)
    print(f"\nFound {len(pdf_links)} PDF links")

    if not pdf_links:
        print("No PDF links found - trying alternative approach...")
        # Fallback: manually known links
        pdf_links = [
            {
                "url": f"https://data.riksdagen.se/fil/JO-{year}",
                "title": f"Ämbetsberättelse {year}",
                "source": "riksdagen",
            }
            for year in range(2020, 2025)
        ]

    # Download and process each PDF
    documents = []
    success_count = 0

    for i, link in enumerate(pdf_links, 1):
        url = link["url"]
        title = link["title"]
        year = extract_year_from_title(title)

        print(f"\n[{i}/{len(pdf_links)}] {title}")
        print(f"  URL: {url}")

        # Generate filename
        if year:
            filename = f"jo_ambetsberattelse_{year}.pdf"
        else:
            safe_title = re.sub(r"[^\w\-]", "_", title)[:50]
            filename = f"jo_{safe_title}.pdf"

        pdf_path = PDF_DIR / filename

        # Download
        try:
            if not pdf_path.exists():
                print("  Downloading...")
                download_pdf(url, pdf_path)
                time.sleep(1)  # Rate limit
            else:
                print("  Already downloaded")

            # Extract text
            text = None
            if HAS_PYMUPDF:
                print("  Extracting text...")
                text = extract_text_from_pdf(pdf_path)
                if text:
                    print(f"  Extracted {len(text):,} characters")

            # Create document record
            doc = {
                "id": f"jo_ambetsberattelse_{year or i}",
                "title": title,
                "year": year,
                "url": url,
                "source": "jo.se",
                "type": "ambetsberattelse",
                "pdf_path": str(pdf_path),
                "text": text[:50000] if text else None,  # Limit text size
                "text_length": len(text) if text else 0,
                "harvested_at": datetime.now().isoformat(),
            }
            documents.append(doc)
            success_count += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            documents.append(
                {
                    "id": f"jo_error_{i}",
                    "title": title,
                    "url": url,
                    "error": str(e),
                    "harvested_at": datetime.now().isoformat(),
                }
            )

    # Save results
    output_file = OUTPUT_DIR / "jo_ambetsberattelser.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "jo.se",
                "type": "ambetsberattelser",
                "harvested_at": datetime.now().isoformat(),
                "total_found": len(pdf_links),
                "total_downloaded": success_count,
                "documents": documents,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("HARVEST COMPLETE")
    print("=" * 70)
    print(f"Found:      {len(pdf_links)} PDFs")
    print(f"Downloaded: {success_count}")
    print(f"Output:     {output_file}")
    print(f"PDFs:       {PDF_DIR}")
    print("=" * 70)

    return documents


if __name__ == "__main__":
    main()
