#!/usr/bin/env python3
"""
Verify ChromaDB content for Försäkringskassan documents
"""

import json

import chromadb
from chromadb.config import Settings

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"


def main():
    # Connect to ChromaDB
    client = chromadb.PersistentClient(
        path=CHROMADB_PATH, settings=Settings(anonymized_telemetry=False)
    )

    collection = client.get_collection(name=COLLECTION_NAME)

    # Get all items
    results = collection.get()

    # Filter for Försäkringskassan documents
    fk_docs = [
        {
            "id": results["ids"][i],
            "metadata": results["metadatas"][i],
            "text_length": len(results["documents"][i]) if results["documents"][i] else 0,
        }
        for i in range(len(results["ids"]))
        if results["metadatas"][i].get("source") == "forsakringskassan"
    ]

    # Statistics
    stats = {
        "total_documents": len(fk_docs),
        "by_type": {},
        "by_year": {},
        "total_text_size": sum(doc["text_length"] for doc in fk_docs),
        "sample_documents": fk_docs[:5],  # First 5 as sample
    }

    # Count by type
    for doc in fk_docs:
        doc_type = doc["metadata"].get("type", "unknown")
        stats["by_type"][doc_type] = stats["by_type"].get(doc_type, 0) + 1

        year = doc["metadata"].get("year")
        if year:
            stats["by_year"][year] = stats["by_year"].get(year, 0) + 1

    # Print report
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
