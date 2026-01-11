#!/usr/bin/env python3
"""
Import JSON scrape data to ChromaDB
Workaround for ChromaDB segfault during scraping
"""

import json
import sys


def import_to_chromadb(json_file: str):
    """Import JSON file to ChromaDB"""

    # Import here to isolate potential crashes
    import chromadb
    from chromadb.config import Settings

    print(f"Loading JSON file: {json_file}")
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    print(f"\nFound {data['total_documents']} documents to import")
    print(f"Source: {data['source']}")
    print(f"Scraped at: {data['scraped_at']}")

    # Connect to ChromaDB
    print("\nConnecting to ChromaDB...")
    client = chromadb.PersistentClient(
        path="./chromadb_data", settings=Settings(anonymized_telemetry=False)
    )

    # Get or create collection
    try:
        collection = client.get_collection("swedish_gov_docs")
        print("✅ Connected to existing collection: swedish_gov_docs")
    except Exception:
        collection = client.create_collection("swedish_gov_docs")
        print("✅ Created new collection: swedish_gov_docs")

    # Import documents
    print("\nImporting documents...")
    imported = 0
    skipped = 0

    for doc in data["documents"]:
        doc_id = doc["id"]

        # Check if already exists
        try:
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                print(f"  ⏭️  Skipping duplicate: {doc['title'][:60]}...")
                skipped += 1
                continue
        except Exception:
            pass

        # Add document
        try:
            collection.add(
                ids=[doc_id],
                documents=[doc["text"]],
                metadatas=[
                    {
                        "source": doc["source"],
                        "url": doc["url"],
                        "title": doc["title"][:500],
                        "doc_type": doc["type"],
                        "scraped_at": data["scraped_at"],
                    }
                ],
            )
            imported += 1
            print(f"  ✅ Imported: {doc['title'][:60]}...")
        except Exception as e:
            print(f"  ❌ Failed to import {doc['title'][:60]}: {e}")

    print("\n" + "=" * 80)
    print("IMPORT COMPLETE")
    print("=" * 80)
    print(f"Imported: {imported}")
    print(f"Skipped (duplicates): {skipped}")
    print(f"Total in collection: {collection.count()}")

    return {"imported": imported, "skipped": skipped, "total": collection.count()}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_json_to_chromadb.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    import_to_chromadb(json_file)
