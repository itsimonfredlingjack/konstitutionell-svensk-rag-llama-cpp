#!/usr/bin/env python3
"""Verify Naturvårdsverket data in ChromaDB"""

import json

import chromadb

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"

client = chromadb.PersistentClient(path=CHROMADB_PATH)
collection = client.get_collection(name=COLLECTION_NAME)

# Query for Naturvårdsverket documents
results = collection.get(where={"source": "naturvardsverket"}, limit=1000)

total_count = len(results["ids"])

# Count by document type
doc_types = {}
for meta in results["metadatas"]:
    dt = meta.get("doc_type", "unknown")
    doc_types[dt] = doc_types.get(dt, 0) + 1

# Sample documents
samples = []
for i in range(min(5, total_count)):
    samples.append(
        {
            "id": results["ids"][i],
            "title": results["metadatas"][i].get("title", "N/A"),
            "url": results["metadatas"][i].get("url", "N/A"),
            "type": results["metadatas"][i].get("doc_type", "N/A"),
        }
    )

report = {
    "collection": COLLECTION_NAME,
    "source": "naturvardsverket",
    "total_documents": total_count,
    "document_types": doc_types,
    "samples": samples,
}

print(json.dumps(report, indent=2, ensure_ascii=False))
