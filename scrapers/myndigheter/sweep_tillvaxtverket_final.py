#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET FINAL
Improved link filtering and deduplication
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def is_valid_document(href, text):
    """Check if link is a valid document"""
    # Exclude pagination and navigation
    if not text or len(text) < 5:
        return False

    exclude_patterns = ["nästa", "previous", "sida", "page=", "tillbaka", "back", "home", "start"]

    if any(x in text.lower() for x in exclude_patterns):
        return False

    if any(x in href.lower() for x in exclude_patterns):
        return False

    # Include only publication patterns
    include_patterns = [
        "/publikationer/publikationer",
        "/publikationer/arkiveradepublikationer/publikationer",
        ".pdf",
        "/rapport",
        "/analys",
    ]

    return any(x in href.lower() for x in include_patterns)


def scrape_publication_list(base_url, headers, max_pages=30):
    """Scrape paginated publication list"""
    documents = []
    seen_urls = set()

    for page in range(max_pages):
        try:
            if page == 0:
                url = base_url
            else:
                separator = "&" if "?" in base_url else "?"
                url = f"{base_url}{separator}page={page}"

            print(f"Scraping page {page}...")
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            found_docs = 0

            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text(strip=True)

                if not is_valid_document(href, text):
                    continue

                full_url = urljoin(url, href)

                # Skip duplicates
                if full_url in seen_urls:
                    continue

                seen_urls.add(full_url)

                doc_id = hashlib.md5(full_url.encode()).hexdigest()

                # Classify document type
                doc_type = "publication"
                if href.endswith(".pdf"):
                    doc_type = "pdf"
                elif "statistik" in text.lower() or "statistik" in href.lower():
                    doc_type = "statistics"
                elif "rapport" in text.lower() or "rapport" in href.lower():
                    doc_type = "report"
                elif "analys" in text.lower() or "analys" in href.lower():
                    doc_type = "analysis"
                elif "vagledning" in text.lower() or "vagledning" in href.lower():
                    doc_type = "guidance"

                documents.append(
                    {
                        "id": doc_id,
                        "url": full_url,
                        "title": text,
                        "source": "tillvaxtverket",
                        "type": doc_type,
                        "scraped_at": datetime.now().isoformat(),
                    }
                )
                found_docs += 1

            print(f"  Found {found_docs} new documents")

            if found_docs == 0:
                print("  No new documents, stopping pagination")
                break

            time.sleep(1)

        except Exception as e:
            print(f"  Error: {e}")
            break

    return documents


def main():
    print("=== TILLVÄXTVERKET FINAL SWEEP ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    sections = [
        {
            "name": "Current Publications",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html",
        },
        {
            "name": "Archived Publications",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer/arkiveradepublikationer.1576.html",
        },
    ]

    all_documents = []

    for section in sections:
        print(f"\n--- {section['name']} ---")
        docs = scrape_publication_list(section["url"], headers)
        all_documents.extend(docs)
        print(f"Section total: {len(docs)} documents")

    # Final deduplication by ID
    unique_docs = {d["id"]: d for d in all_documents}
    documents = list(unique_docs.values())

    print(f"\n=== TOTAL UNIQUE DOCUMENTS: {len(documents)} ===")

    # Type breakdown
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
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
