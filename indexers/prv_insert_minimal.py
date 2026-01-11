#!/usr/bin/env python3
import json
import sys

sys.path.insert(0, "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/backend")

# Use backend's ChromaDB setup via RetrievalService
import asyncio

from app.services.retrieval_service import get_retrieval_service


async def main():
    # Load scraped data
    with open(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/prv_scrape_20251207_210724.json"
    ) as f:
        data = json.load(f)

    documents = data.get("documents", [])
    print(f"Loaded {len(documents)} documents")

    # Get ChromaDB client from backend via RetrievalService
    retrieval_service = get_retrieval_service()
    await retrieval_service.initialize()
    client = retrieval_service._chromadb_client
    collection = client.get_or_create_collection("swedish_gov_docs")

    print(f"Current collection size: {collection.count()}")

    # Insert in batches
    ids = [d["id"] for d in documents if "id" in d and "content" in d]
    contents = [d["content"] for d in documents if "id" in d and "content" in d]
    metas = [
        {k: str(v) for k, v in d.items() if k not in ["id", "content"]}
        for d in documents
        if "id" in d and "content" in d
    ]

    for i in range(0, len(ids), 50):
        collection.upsert(
            ids=ids[i : i + 50], documents=contents[i : i + 50], metadatas=metas[i : i + 50]
        )
        print(f"Batch {i // 50 + 1}/{(len(ids) - 1) // 50 + 1}")

    print(f"Final count: {collection.count()}")


if __name__ == "__main__":
    asyncio.run(main())
