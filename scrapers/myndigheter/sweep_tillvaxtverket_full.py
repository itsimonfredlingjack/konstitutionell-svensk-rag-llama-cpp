#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET FULL
Complete scrape including all archived publications
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def scrape_publication_list(base_url, headers, max_pages=20):
    """Scrape paginated publication list"""
    documents = []
    page = 0

    while page < max_pages:
        try:
            # Tillväxtverket uses ?page= pagination
            if page == 0:
                url = base_url
            else:
                separator = "&" if "?" in base_url else "?"
                url = f"{base_url}{separator}page={page}"

            print(f"Scraping page {page}: {url}")
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            found_docs = 0

            # Find all links
            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text(strip=True)

                if not text or len(text) < 5:
                    continue

                full_url = urljoin(url, href)

                # Match publication patterns
                is_pub = any(
                    x in href.lower()
                    for x in [
                        "/publikationer/publikationer",
                        "/publikationer/arkiveradepublikationer",
                        ".pdf",
                    ]
                )

                if is_pub:
                    doc_id = hashlib.md5(full_url.encode()).hexdigest()

                    doc_type = "publication"
                    if href.endswith(".pdf"):
                        doc_type = "pdf"
                    elif "rapport" in text.lower():
                        doc_type = "report"
                    elif "statistik" in text.lower():
                        doc_type = "statistics"
                    elif "analys" in text.lower():
                        doc_type = "analysis"

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

            print(f"  Found {found_docs} documents on page {page}")

            # Check for next page
            next_link = soup.find("a", string="Nästa") or soup.find("a", class_="next")
            if not next_link and found_docs == 0:
                break

            page += 1
            time.sleep(1)

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break

    return documents


def main():
    print("=== TILLVÄXTVERKET FULL SWEEP ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Publication sections to scrape
    sections = [
        {
            "name": "Current Publications",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html",
        },
        {
            "name": "Archived Publications 2015-2020",
            "url": "https://tillvaxtverket.se/tillvaxtverket/publikationer/arkiveradepublikationer.1576.html",
        },
        {
            "name": "Statistics & Analysis",
            "url": "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys/trenderochanalyser.1625.html",
        },
    ]

    all_documents = []

    for section in sections:
        print(f"\n--- {section['name']} ---")
        docs = scrape_publication_list(section["url"], headers, max_pages=30)
        all_documents.extend(docs)
        print(f"Total from {section['name']}: {len(docs)}")

    # Remove duplicates
    unique_docs = {d["id"]: d for d in all_documents}
    documents = list(unique_docs.values())

    print(f"\n=== TOTAL UNIQUE DOCUMENTS: {len(documents)} ===")

    # Generate summary
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

    # Save files
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_sweep.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    docs_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_docs.json"
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print("\nFiles saved:")
    print(f"  Summary: {output_path}")
    print(f"  Full docs: {docs_path}")
    print(f"\n{json.dumps(summary, indent=2, ensure_ascii=False)}")

    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents (expected >100)")
    else:
        print(f"\n✓ SUCCESS: {len(documents)} documents collected")


if __name__ == "__main__":
    main()
