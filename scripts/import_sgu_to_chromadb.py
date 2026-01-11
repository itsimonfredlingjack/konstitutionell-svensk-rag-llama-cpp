#!/usr/bin/env python3
"""
Import SGU documents from JSON to ChromaDB
"""

import hashlib
import json
import logging
from pathlib import Path

import chromadb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "sgu_documents"  # Separate collection to avoid issues with large swedish_gov_docs
JSON_PATH = Path(__file__).parent / "sgu_documents.json"


def generate_doc_id(url: str, title: str) -> str:
    content = f"{url}|{title}".encode()
    return hashlib.sha256(content).hexdigest()[:16]


def main():
    logger.info("=" * 60)
    logger.info("SGU IMPORT TO CHROMADB")
    logger.info("=" * 60)

    # Load documents
    logger.info(f"Loading documents from: {JSON_PATH}")
    with open(JSON_PATH, encoding="utf-8") as f:
        documents_data = json.load(f)

    logger.info(f"Loaded {len(documents_data)} documents")

    # Connect to ChromaDB
    logger.info(f"Connecting to ChromaDB: {CHROMADB_PATH}")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Swedish government documents from multiple sources"},
    )

    logger.info(f"Collection: {COLLECTION_NAME}")
    logger.info(f"Existing documents in collection: {collection.count()}")

    # Prepare batch data
    ids = []
    documents = []
    metadatas = []

    for doc in documents_data:
        doc_id = generate_doc_id(doc["url"], doc["title"])
        ids.append(doc_id)
        documents.append(doc["content"])
        metadatas.append(
            {
                "title": doc["title"],
                "url": doc["url"],
                "source": "sgu",
                "doc_type": doc["doc_type"],
                "publication_date": doc.get("publication_date", "unknown"),
                "format": "pdf",
                "scraped_at": doc["scraped_at"],
            }
        )

    # Insert in batches
    batch_size = 50
    total_batches = (len(ids) - 1) // batch_size + 1

    logger.info(f"\nInserting {len(ids)} documents in {total_batches} batches...")

    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_docs = documents[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]

        try:
            collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
            batch_num = i // batch_size + 1
            logger.info(f"✓ Batch {batch_num}/{total_batches} ({len(batch_ids)} docs)")
        except Exception as e:
            logger.error(f"✗ Error in batch {i // batch_size + 1}: {e}")

    # Verify
    final_count = collection.count()
    logger.info(f"\nFinal collection count: {final_count:,}")
    logger.info("=" * 60)
    logger.info("IMPORT COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
