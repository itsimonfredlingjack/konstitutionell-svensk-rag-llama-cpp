#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET DEEP
Two-stage scrape:
1. Get all publication pages
2. Extract PDFs from each page
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def extract_pdf_from_page(url, headers):
    """Extract PDF link and metadata from publication page"""
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        pdfs = []

        # Find PDF download links
        for link in soup.find_all("a", href=True):
            href = link.get("href")
            if ".pdf" in href.lower() or "/download/" in href:
                full_url = urljoin(url, href)
                pdfs.append({"url": full_url, "text": link.get_text(strip=True) or "PDF"})

        return pdfs

    except Exception as e:
        print(f"    Error extracting PDF: {e}")
        return []


def scrape_publication_list(base_url, headers, max_pages=50):
    """Get all publication pages"""
    pub_pages = []
    seen_urls = set()

    for page in range(max_pages):
        try:
            if page == 0:
                url = base_url
            else:
                separator = "&" if "?" in base_url else "?"
                url = f"{base_url}{separator}page={page}"

            print(f"  Page {page}...", end=" ")
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            found = 0

            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text(strip=True)

                # Match publication page URLs
                is_pub_page = (
                    "/publikationer/publikationer" in href
                    or "/publikationer/arkiveradepublikationer/publikationer" in href
                )

                # Exclude navigation
                is_nav = any(x in text.lower() for x in ["nästa", "previous", "sida"])

                if is_pub_page and not is_nav and len(text) > 5:
                    full_url = urljoin(url, href)

                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        pub_pages.append({"url": full_url, "title": text})
                        found += 1

            print(f"{found} new publications")

            if found == 0:
                break

            time.sleep(0.5)

        except Exception as e:
            print(f"  Error: {e}")
            break

    return pub_pages


def main():
    print("=== TILLVÄXTVERKET DEEP SWEEP ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Stage 1: Get all publication pages
    print("Stage 1: Scraping publication lists")

    sections = [
        {
            "name": "Current",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html",
        },
        {
            "name": "Archived",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer/arkiveradepublikationer.1576.html",
        },
    ]

    all_pub_pages = []

    for section in sections:
        print(f"\n{section['name']} Publications:")
        pages = scrape_publication_list(section["url"], headers)
        all_pub_pages.extend(pages)
        print(f"  Total: {len(pages)}")

    print(f"\nTotal publication pages found: {len(all_pub_pages)}")

    # Stage 2: Extract PDFs from each publication page
    print(f"\nStage 2: Extracting PDFs from {len(all_pub_pages)} pages")

    documents = []

    for i, pub in enumerate(all_pub_pages):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(all_pub_pages)}")

        # Add the publication page itself
        doc_id = hashlib.md5(pub["url"].encode()).hexdigest()
        documents.append(
            {
                "id": doc_id,
                "url": pub["url"],
                "title": pub["title"],
                "source": "tillvaxtverket",
                "type": "publication_page",
                "scraped_at": datetime.now().isoformat(),
            }
        )

        # Extract PDFs
        pdfs = extract_pdf_from_page(pub["url"], headers)
        for pdf in pdfs:
            pdf_id = hashlib.md5(pdf["url"].encode()).hexdigest()
            documents.append(
                {
                    "id": pdf_id,
                    "url": pdf["url"],
                    "title": f"{pub['title']} (PDF)",
                    "source": "tillvaxtverket",
                    "type": "pdf",
                    "parent": pub["url"],
                    "scraped_at": datetime.now().isoformat(),
                }
            )

        time.sleep(0.3)

    # Deduplication
    unique_docs = {d["id"]: d for d in documents}
    documents = list(unique_docs.values())

    print(f"\nTotal documents: {len(documents)}")

    # Summary
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
        "publication_pages": len(all_pub_pages),
        "types": {},
        "sample_docs": documents[:50],
    }

    for doc in documents:
        doc_type = doc["type"]
        summary["types"][doc_type] = summary["types"].get(doc_type, 0) + 1

    # Save
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_sweep.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    docs_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_docs.json"
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print("\nFiles saved:")
    print(f"  {output_path}")
    print(f"  {docs_path}")

    print("\nType breakdown:")
    for doc_type, count in sorted(summary["types"].items(), key=lambda x: -x[1]):
        print(f"  {doc_type}: {count}")

    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents (expected >100)")
    else:
        print(f"\n✓ SUCCESS: Collected {len(documents)} documents")


if __name__ == "__main__":
    main()
