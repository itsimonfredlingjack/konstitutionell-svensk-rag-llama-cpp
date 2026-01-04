#!/usr/bin/env python3
"""
Index Naturvårdsverket documents to ChromaDB
Uses smaller batches to avoid segfault
"""

import json
import logging
import time

import chromadb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"
DOCS_FILE = "naturvardsverket_docs_20251207_191546.json"


def index_to_chromadb():
    # Load documents
    logger.info(f"Loading documents from {DOCS_FILE}")
    with open(DOCS_FILE, encoding="utf-8") as f:
        documents = json.load(f)

    logger.info(f"Loaded {len(documents)} documents")

    # Connect to ChromaDB
    logger.info(f"Connecting to ChromaDB at {CHROMADB_PATH}")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    # Get or create collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
    )

    # Prepare data
    ids = []
    metadatas = []
    documents_text = []

    for doc in documents:
        ids.append(doc["id"])
        metadatas.append(
            {
                "source": "naturvardsverket",
                "url": doc["url"],
                "title": doc["title"],
                **doc["metadata"],
            }
        )
        documents_text.append(doc["content"])

    # Insert in VERY small batches (avoid segfault)
    batch_size = 10
    total_batches = (len(ids) + batch_size - 1) // batch_size

    for i in range(0, len(ids), batch_size):
        batch_num = i // batch_size + 1
        batch_ids = ids[i : i + batch_size]
        batch_metas = metadatas[i : i + batch_size]
        batch_docs = documents_text[i : i + batch_size]

        try:
            collection.upsert(ids=batch_ids, metadatas=batch_metas, documents=batch_docs)
            logger.info(f"Batch {batch_num}/{total_batches}: Indexed {len(batch_ids)} documents")
            time.sleep(0.1)  # Small delay between batches
        except Exception as e:
            logger.error(f"Error in batch {batch_num}: {e}")
            continue

    logger.info(f"Successfully indexed {len(documents)} documents to ChromaDB")

    # Verify
    count = collection.count()
    logger.info(f"Collection now contains {count} total documents")

    return {"status": "success", "documents_indexed": len(documents), "total_in_collection": count}


if __name__ == "__main__":
    result = index_to_chromadb()
    print(json.dumps(result, indent=2))
