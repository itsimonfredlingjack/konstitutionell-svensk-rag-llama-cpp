#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET V2
Deep scraping with corrected URLs
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def scrape_page(url, headers, visited=set()):
    """Recursively scrape a page for documents"""
    if url in visited:
        return []

    visited.add(url)
    documents = []

    try:
        print(f"Scraping {url}...")
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link.get("href")
            text = link.get_text(strip=True)

            if not text or len(text) < 5:
                continue

            full_url = urljoin(url, href)

            # PDF or document link
            if href.endswith(".pdf"):
                doc_id = hashlib.md5(full_url.encode()).hexdigest()
                documents.append(
                    {
                        "id": doc_id,
                        "url": full_url,
                        "title": text,
                        "source": "tillvaxtverket",
                        "type": "pdf",
                        "scraped_at": datetime.now().isoformat(),
                    }
                )

            # Publication pages
            elif any(x in href.lower() for x in ["/publikationer/", "/rapport", "/analys"]):
                doc_id = hashlib.md5(full_url.encode()).hexdigest()

                doc_type = "document"
                if "publikation" in href.lower():
                    doc_type = "publication"
                elif "rapport" in href.lower():
                    doc_type = "report"
                elif "analys" in href.lower():
                    doc_type = "analysis"
                elif "statistik" in href.lower():
                    doc_type = "statistics"

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

    except Exception as e:
        print(f"  Error: {e}")

    return documents


def main():
    print("=== TILLVÄXTVERKET SWEEP V2 ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    # Corrected URLs based on WebFetch
    base_urls = [
        "https://tillvaxtverket.se/tillvaxtverket/publikationer.publikation.html",
        "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys.1987.html",
        "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys/statistikomforetag.1521.html",
        "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys/statistikomregionalutveckling.1522.html",
        "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys/statistikomturism.1523.html",
        "https://tillvaxtverket.se/tillvaxtverket/statistikochanalys/trenderochanalyser.1625.html",
        "https://tillvaxtverket.se/tillvaxtverket/guiderochverktyg.2171.html",
    ]

    all_documents = []
    visited = set()

    for url in base_urls:
        docs = scrape_page(url, headers, visited)
        all_documents.extend(docs)
        print(f"  Found {len(docs)} documents")
        time.sleep(1)

    # Remove duplicates
    unique_docs = {d["id"]: d for d in all_documents}
    documents = list(unique_docs.values())

    print(f"\nTotal unique documents: {len(documents)}")

    # Generate summary
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
        "types": {},
        "sample_docs": documents[:30],
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

    print(f"\nSummary: {output_path}")
    print(f"Full docs: {docs_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents (expected >100)")
        print("Recommendation: Expand to archive pages and subdirectories")


if __name__ == "__main__":
    main()
