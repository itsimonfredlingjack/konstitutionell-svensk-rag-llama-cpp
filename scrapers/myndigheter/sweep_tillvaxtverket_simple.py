#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET
Scrapes documents from tillvaxtverket.se (NO ChromaDB)
"""

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def main():
    print("=== TILLVÄXTVERKET SWEEP ===\n")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    urls = [
        "https://tillvaxtverket.se/vara-tjanster/publikationer.html",
        "https://tillvaxtverket.se/statistik-och-analys.html",
        "https://tillvaxtverket.se/om-tillvaxtverket/vagledningar.html",
        "https://tillvaxtverket.se/om-tillvaxtverket/foreskrifter.html",
        "https://tillvaxtverket.se/statistik-och-analys/statistik-om-naringslivet.html",
        "https://tillvaxtverket.se/statistik-och-analys/rapporter.html",
    ]

    documents = []

    for base_url in urls:
        try:
            print(f"Scraping {base_url}...")
            r = requests.get(base_url, headers=headers, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text(strip=True)

                if not text or len(text) < 10:
                    continue

                full_url = urljoin(base_url, href)

                # Match document patterns
                is_doc = any(
                    x in href.lower()
                    for x in [
                        ".pdf",
                        "/publikationer/",
                        "/statistik/",
                        "/vagledning",
                        "/rapport",
                        "/analys",
                    ]
                )

                if is_doc:
                    doc_id = hashlib.md5(full_url.encode()).hexdigest()

                    doc_type = "document"
                    if "publikation" in href.lower():
                        doc_type = "publication"
                    elif "statistik" in href.lower():
                        doc_type = "statistics"
                    elif "vagledning" in href.lower():
                        doc_type = "guidance"
                    elif "foreskrift" in href.lower():
                        doc_type = "regulation"
                    elif "rapport" in href.lower():
                        doc_type = "report"

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

            print(f"  Found {len(documents)} documents so far")
            time.sleep(1)

        except Exception as e:
            print(f"Error: {e}")

    # Remove duplicates
    unique_docs = {d["id"]: d for d in documents}
    documents = list(unique_docs.values())

    print(f"\nTotal unique documents: {len(documents)}")

    # Generate summary
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
        "types": {},
        "sample_docs": documents[:20],
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

    # Save full docs
    docs_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_docs.json"
    with open(docs_path, "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2, ensure_ascii=False)

    print(f"\nSummary: {output_path}")
    print(f"Full docs: {docs_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents (expected >100)")


if __name__ == "__main__":
    main()
