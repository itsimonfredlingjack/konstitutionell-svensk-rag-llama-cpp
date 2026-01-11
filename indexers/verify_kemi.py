#!/usr/bin/env python3
"""Verify Kemi documents in ChromaDB"""

import chromadb

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

try:
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_collection("swedish_gov_docs")

    # Query for kemi documents
    results = collection.get(where={"source": "kemi"}, limit=100)

    count = len(results["ids"])
    print(f"\n{'=' * 70}")
    print(f"KEMI DOCUMENTS IN CHROMADB: {count}")
    print(f"{'=' * 70}\n")

    # Group by doc_type
    by_type = {}
    for metadata in results["metadatas"]:
        doc_type = metadata.get("doc_type", "unknown")
        by_type[doc_type] = by_type.get(doc_type, 0) + 1

    print("BY TYPE:")
    for doc_type, cnt in sorted(by_type.items()):
        print(f"  {doc_type:<20} {cnt:>3}")

    print(f"\n{'=' * 70}")
    print("SAMPLE DOCUMENTS:")
    print(f"{'=' * 70}\n")

    # Show first 5
    for i in range(min(5, count)):
        meta = results["metadatas"][i]
        doc = results["documents"][i]
        print(f"{i + 1}. {meta.get('title', 'No title')}")
        print(f"   Type: {meta.get('doc_type', 'unknown')}")
        print(f"   Date: {meta.get('date', 'unknown')}")
        print(f"   URL:  {meta.get('url', 'unknown')}")
        print(f"   Text: {doc[:150]}...")
        print()

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
