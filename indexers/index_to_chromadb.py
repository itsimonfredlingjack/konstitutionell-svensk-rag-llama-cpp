#!/usr/bin/env python3
"""
INDEX TO CHROMADB
Takes scraped Riksbanken data and indexes to ChromaDB
"""

import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"


def load_scraped_data(json_file: str) -> list:
    """Load publications from JSON file"""
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("all_publications", data.get("publications", []))


def index_to_chromadb(publications: list):
    """Index publications to ChromaDB"""
    print("Initializing ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        print(f"Using existing collection: {COLLECTION_NAME}")
    except Exception:
        collection = client.create_collection(
            name=COLLECTION_NAME, metadata={"description": "Swedish government documents"}
        )
        print(f"Created new collection: {COLLECTION_NAME}")

    print("Loading embedding model (KBLab/sentence-bert-swedish-cased)...")
    embedding_model = SentenceTransformer("KBLab/sentence-bert-swedish-cased")

    print(f"\nIndexing {len(publications)} publications...")

    batch_size = 10
    indexed = 0
    errors = []

    for i in range(0, len(publications), batch_size):
        batch = publications[i : i + batch_size]

        try:
            ids = []
            documents = []
            metadatas = []
            embeddings = []

            for pub in batch:
                # Create unique ID
                doc_id = f"{pub['source']}_{pub['pub_type']}_{hash(pub['url'])}"
                ids.append(doc_id)

                # Full text
                full_text = f"{pub['title']}\n\n{pub['content']}"
                documents.append(full_text)

                # Metadata
                metadatas.append(
                    {
                        "source": pub["source"],
                        "title": pub["title"],
                        "url": pub["url"],
                        "pub_type": pub["pub_type"],
                        "date": pub["date"],
                        "authors": pub["authors"],
                    }
                )

                # Generate embedding
                embedding = embedding_model.encode(full_text).tolist()
                embeddings.append(embedding)

            # Add to collection
            collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

            indexed += len(batch)
            print(f"  Indexed {indexed}/{len(publications)}...")

        except Exception as e:
            errors.append(str(e))
            print(f"  ERROR in batch: {e}")

    print(f"\n{'=' * 60}")
    print("INDEXING COMPLETE")
    print(f"Total indexed: {indexed}")
    print(f"Errors: {len(errors)}")
    print(f"{'=' * 60}")

    if errors:
        print("\nErrors encountered:")
        for err in errors[:5]:
            print(f"  - {err}")

    return indexed, errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 index_to_chromadb.py <scraped_data.json>")
        sys.exit(1)

    json_file = sys.argv[1]

    if not Path(json_file).exists():
        print(f"ERROR: File not found: {json_file}")
        sys.exit(1)

    publications = load_scraped_data(json_file)
    print(f"Loaded {len(publications)} publications from {json_file}")

    indexed, errors = index_to_chromadb(publications)

    result = {
        "status": "OK" if indexed >= 100 else "FLAGGAD",
        "docs_indexed": indexed,
        "errors": errors,
    }

    print("\nFinal result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
