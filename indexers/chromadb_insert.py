#!/usr/bin/env python3
"""
ChromaDB Insertion Script - Load scraped documents
Works around segfault issues by being minimal and focused
"""

import json
import sys
from pathlib import Path


def load_and_insert(json_file: str):
    """Load JSON and insert to ChromaDB"""
    print(f"Loading: {json_file}")

    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get("documents", [])
    if not documents:
        print("No documents found in JSON!")
        return

    print(f"Found {len(documents)} documents")

    # Import ChromaDB AFTER loading JSON
    import chromadb

    CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
    COLLECTION_NAME = "swedish_gov_docs"

    print(f"Connecting to ChromaDB: {CHROMADB_PATH}")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    print(f"Getting collection: {COLLECTION_NAME}")
    collection = client.get_or_create_collection(COLLECTION_NAME)

    print(f"Current collection size: {collection.count()}")

    # Prepare data
    ids = []
    contents = []
    metadatas = []

    for doc in documents:
        if "id" not in doc or "content" not in doc:
            continue

        ids.append(doc["id"])
        contents.append(doc["content"])

        # Metadata (everything except id and content)
        meta = {k: str(v) for k, v in doc.items() if k not in ["id", "content"]}
        metadatas.append(meta)

    print(f"Inserting {len(ids)} documents...")

    # Batch insert (ChromaDB handles deduplication via ID)
    BATCH_SIZE = 50
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i : i + BATCH_SIZE]
        batch_contents = contents[i : i + BATCH_SIZE]
        batch_metas = metadatas[i : i + BATCH_SIZE]

        collection.upsert(ids=batch_ids, documents=batch_contents, metadatas=batch_metas)
        print(f"  Inserted batch {i//BATCH_SIZE + 1}/{(len(ids)-1)//BATCH_SIZE + 1}")

    final_count = collection.count()
    print(f"\nDone! Collection now has {final_count} documents")

    return {"inserted": len(ids), "total_in_collection": final_count}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 chromadb_insert.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    if not Path(json_file).exists():
        print(f"File not found: {json_file}")
        sys.exit(1)

    result = load_and_insert(json_file)
    print(json.dumps(result, indent=2))
