#!/usr/bin/env python3
"""
Load BO documents into ChromaDB
"""

import json
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings


def load_to_chromadb(json_file: str):
    """Load documents from JSON into ChromaDB"""

    # Load JSON
    with open(json_file, encoding="utf-8") as f:
        documents = json.load(f)

    print(f"Loaded {len(documents)} documents from {json_file}")

    # ChromaDB setup
    chroma_path = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
    client = chromadb.PersistentClient(
        path=str(chroma_path), settings=Settings(anonymized_telemetry=False)
    )

    # Get or create collection
    collection = client.get_or_create_collection(
        name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
    )

    print(f"Collection: {collection.name} (existing count: {collection.count()})")

    # Prepare documents for insertion
    ids = []
    texts = []
    metadatas = []

    for doc in documents:
        # Use doc_id as unique identifier
        doc_id = f"bo_{doc['doc_id']}"
        ids.append(doc_id)

        # Text content
        text = doc["text_content"]
        texts.append(text)

        # Metadata
        meta = {
            "title": doc["title"],
            "url": doc["url"],
            "page_url": doc.get("page_url", doc["url"]),
            "source": "barnombudsmannen",
            "source_full": "Barnombudsmannen",
            "doc_type": doc["doc_type"],
            "year": str(doc.get("year", "")),
            "date": doc.get("date", ""),
            "description": doc.get("description", ""),
            "scraped_at": doc["scraped_at"],
        }
        metadatas.append(meta)

    # Insert in batches
    batch_size = 100
    added_count = 0
    updated_count = 0

    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_texts = texts[i : i + batch_size]
        batch_metas = metadatas[i : i + batch_size]

        try:
            # Try to upsert (add or update)
            collection.upsert(ids=batch_ids, documents=batch_texts, metadatas=batch_metas)
            added_count += len(batch_ids)
            print(f"  Added batch {i//batch_size + 1}: {len(batch_ids)} documents")

        except Exception as e:
            print(f"  Error adding batch {i//batch_size + 1}: {e}")
            # Try individually
            for doc_id, text, meta in zip(batch_ids, batch_texts, batch_metas):
                try:
                    collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
                    added_count += 1
                except Exception as e2:
                    print(f"    Error adding {doc_id}: {e2}")

    print(f"\n{'='*60}")
    print("CHROMADB LOAD COMPLETE")
    print(f"{'='*60}")
    print(f"Documents added/updated: {added_count}")
    print(f"Collection total count: {collection.count()}")

    # Verify BO documents
    try:
        bo_results = collection.get(where={"source": "barnombudsmannen"}, limit=1000)
        print(f"BO documents in collection: {len(bo_results['ids'])}")
    except Exception as e:
        print(f"Could not count BO documents: {e}")

    return added_count


if __name__ == "__main__":
    # Use latest JSON file
    scraped_dir = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/scraped_data")
    json_files = list(scraped_dir.glob("bo_documents_v2_*.json"))

    if not json_files:
        print("No BO JSON files found!")
        sys.exit(1)

    # Use the latest file
    latest_file = sorted(json_files)[-1]
    print(f"Using file: {latest_file}")

    count = load_to_chromadb(str(latest_file))

    print(f"\n✓ Loaded {count} documents to ChromaDB")
