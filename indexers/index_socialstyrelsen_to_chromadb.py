#!/usr/bin/env python3
"""
Index Socialstyrelsen documents to ChromaDB
"""

import json
import logging
import sys
from datetime import datetime

import chromadb
from chromadb.config import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def index_to_chromadb(
    json_file: str,
    chromadb_path: str = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data",
):
    """Index scraped documents to ChromaDB"""

    logger.info(f"Loading documents from {json_file}")

    with open(json_file, encoding="utf-8") as f:
        documents = json.load(f)

    logger.info(f"Loaded {len(documents)} documents")

    # Initialize ChromaDB
    logger.info(f"Connecting to ChromaDB at {chromadb_path}")
    client = chromadb.PersistentClient(
        path=chromadb_path, settings=Settings(anonymized_telemetry=False)
    )

    # Get or create collection
    collection = client.get_or_create_collection(
        name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
    )

    logger.info("Collection 'swedish_gov_docs' ready")

    # Prepare batch data
    ids = []
    metadatas = []
    documents_text = []

    for i, doc in enumerate(documents):
        doc_id = f"socialstyrelsen_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ids.append(doc_id)

        # Extract metadata
        metadata = {
            "source": "socialstyrelsen",
            "title": doc.get("title", "")[:500],  # ChromaDB metadata limit
            "url": doc.get("url", ""),
            "type": doc.get("type", ""),
            "scraped_at": doc.get("scraped_at", ""),
        }

        # Add foreskrift_id if available
        if "foreskrift_id" in doc:
            metadata["foreskrift_id"] = doc["foreskrift_id"]

        # Add pdf_url if available
        if doc.get("pdf_url"):
            metadata["pdf_url"] = doc["pdf_url"]

        metadatas.append(metadata)

        # Combine title and content for embedding
        text = f"{doc.get('title', '')}\n\n{doc.get('content', '')}"
        documents_text.append(text)

    # Batch upsert
    logger.info(f"Upserting {len(ids)} documents to ChromaDB...")

    batch_size = 100
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_metadatas = metadatas[i : i + batch_size]
        batch_documents = documents_text[i : i + batch_size]

        collection.upsert(ids=batch_ids, metadatas=batch_metadatas, documents=batch_documents)

        logger.info(f"Upserted batch {i//batch_size + 1}/{(len(ids)-1)//batch_size + 1}")

    logger.info("Indexing complete!")

    # Verify
    count = collection.count()
    logger.info(f"Total documents in collection: {count}")

    # Test query
    results = collection.query(query_texts=["föreskrifter"], n_results=3)

    logger.info("\nTest query results (top 3 for 'föreskrifter'):")
    for i, (doc, metadata) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        logger.info(f"{i+1}. {metadata.get('title', 'No title')[:80]}")

    return count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python index_socialstyrelsen_to_chromadb.py <json_file>")
        sys.exit(1)

    json_file = sys.argv[1]
    count = index_to_chromadb(json_file)

    print(f"\n{'='*60}")
    print(f"INDEXING COMPLETE: {count} documents in ChromaDB")
    print(f"{'='*60}")
