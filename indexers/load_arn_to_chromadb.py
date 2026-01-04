#!/usr/bin/env python3
"""
Load ARN documents from JSON report into ChromaDB
Separate script to avoid async/segfault issues
"""

import json
import sys

import chromadb

# Configuration
REPORT_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/arn_scraper_report.json"
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"


def main():
    print("Loading ARN report...")

    # Load report
    with open(REPORT_FILE, encoding="utf-8") as f:
        report = json.load(f)

    # Try to get all documents, fall back to samples
    all_docs = report.get("all_documents", report.get("sample_documents", []))
    total_docs = report["stats"]["total"]

    print(f"Report contains {total_docs} documents")
    print(f"Documents in JSON: {len(all_docs)}")

    if len(all_docs) == 0:
        print("ERROR: No documents found in report")
        return 1

    if len(all_docs) < total_docs:
        print(f"\nWARNING: Only {len(all_docs)}/{total_docs} documents in JSON")

    print("\nConnecting to ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    print(f"Collection '{COLLECTION_NAME}' opened")

    # Prepare data
    ids = []
    documents = []
    metadatas = []

    for doc in all_docs:
        ids.append(doc["id"])
        documents.append(doc["content"][:10000])  # Truncate
        metadatas.append(doc["metadata"])

    print(f"\nUpserting {len(ids)} documents...")
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    print(f"SUCCESS: Stored {len(ids)} ARN documents in ChromaDB")

    # Verify
    arn_count = collection.count()
    print(f"Total documents in collection: {arn_count}")

    # Try to query ARN docs
    try:
        results = collection.get(where={"source": "arn"}, limit=10)
        print(f"ARN documents in collection: {len(results['ids'])}")
    except Exception as e:
        print(f"Could not query ARN docs: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
