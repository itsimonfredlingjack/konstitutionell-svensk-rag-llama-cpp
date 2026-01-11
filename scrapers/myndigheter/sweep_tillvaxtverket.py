#!/usr/bin/env python3
"""
OPERATION MYNDIGHETS-SWEEP - TILLVÄXTVERKET
Scrapes documents from tillvaxtverket.se and stores in ChromaDB
"""

import hashlib
import json
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import chromadb
import requests
from bs4 import BeautifulSoup
from chromadb.config import Settings


def main():
    print("=== TILLVÄXTVERKET SWEEP ===\n")

    # ChromaDB setup with memory-safe settings
    try:
        client = chromadb.PersistentClient(
            path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
            settings=Settings(allow_reset=False, anonymized_telemetry=False, is_persistent=True),
        )

        collection = client.get_or_create_collection(
            name="swedish_gov_docs",
            metadata={"description": "Swedish government documents from multiple agencies"},
        )

        # Count existing
        existing = collection.get(where={"source": "tillvaxtverket"}, limit=1)
        existing_count = collection.count()
        print(f"Total docs in collection: {existing_count}")

    except Exception as e:
        print(f"ChromaDB error: {e}")
        print("Falling back to JSON-only mode")
        collection = None

    # HTTP headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Target URLs
    urls = [
        "https://tillvaxtverket.se/vara-tjanster/publikationer.html",
        "https://tillvaxtverket.se/statistik-och-analys.html",
        "https://tillvaxtverket.se/om-tillvaxtverket/vagledningar.html",
        "https://tillvaxtverket.se/om-tillvaxtverket/foreskrifter.html",
    ]

    documents = []

    # Scrape each page
    for base_url in urls:
        try:
            print(f"Scraping {base_url}...")
            r = requests.get(base_url, headers=headers, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")

            # Find document links
            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text(strip=True)

                # Skip empty or very short links
                if not text or len(text) < 10:
                    continue

                full_url = urljoin(base_url, href)

                # Filter for documents
                if any(
                    x in href.lower()
                    for x in [".pdf", "/publikationer/", "/statistik/", "/vagledning", "/rapport"]
                ):
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

            print(
                f"  Found {len([d for d in documents if d['url'].startswith(base_url[:30])])} documents"
            )
            time.sleep(1)  # Rate limiting

        except Exception as e:
            print(f"Error scraping {base_url}: {e}")

    # Remove duplicates
    unique_docs = {d["id"]: d for d in documents}
    documents = list(unique_docs.values())

    print(f"\nTotal unique documents scraped: {len(documents)}")

    # Insert into ChromaDB if available
    if collection and documents:
        try:
            batch_size = 50  # Smaller batches to avoid segfault
            inserted = 0

            for i in range(0, len(documents), batch_size):
                batch = documents[i : i + batch_size]

                try:
                    collection.upsert(
                        ids=[d["id"] for d in batch],
                        documents=[d["title"] for d in batch],
                        metadatas=[
                            {
                                "url": d["url"],
                                "source": d["source"],
                                "type": d["type"],
                                "scraped_at": d["scraped_at"],
                            }
                            for d in batch
                        ],
                    )
                    inserted += len(batch)
                    print(f"Inserted batch {i // batch_size + 1} ({inserted} total)")
                    time.sleep(0.5)  # Give ChromaDB time to write

                except Exception as e:
                    print(f"Error inserting batch {i // batch_size + 1}: {e}")

            # Final count
            try:
                final_count = collection.count()
                print(f"\nTotal docs in ChromaDB: {final_count}")
            except:
                print("Could not get final count")

        except Exception as e:
            print(f"ChromaDB insertion error: {e}")

    # Generate summary
    summary = {
        "agency": "Tillväxtverket",
        "url": "tillvaxtverket.se",
        "scraped_at": datetime.now().isoformat(),
        "documents_scraped": len(documents),
        "types": {},
        "sample_docs": documents[:10] if documents else [],
    }

    for doc in documents:
        doc_type = doc["type"]
        summary["types"][doc_type] = summary["types"].get(doc_type, 0) + 1

    # Save to file
    output_path = (
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/tillvaxtverket_sweep.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\nSummary saved to: {output_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # FLAG if under 100 docs
    if len(documents) < 100:
        print(f"\n⚠️  FLAG: Only {len(documents)} documents scraped (expected >100)")
        print("Consider expanding URL list or scraping deeper")

    return 0


if __name__ == "__main__":
    sys.exit(main())
