#!/usr/bin/env python3
"""
Index Kemikalieinspektionen documents to ChromaDB
Uses cached data from previous scrape
"""

import json
from datetime import datetime
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"


def index_from_cache():
    """Re-run scraper to get documents and index them"""
    print("Running scraper to collect documents...")

    # Import and run the scraper
    import sys

    sys.path.insert(0, "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI")

    # Temporarily disable the main block
    import scrape_kemi

    scraper = scrape_kemi.KemiScraper()

    # Only scrape, don't index yet
    print("\n SCRAPING KIFS...")
    kifs_docs = scraper.scrape_kifs_regulations()
    scraper.documents.extend(kifs_docs)

    print("\n SCRAPING PUBLICATIONS...")
    pub_docs = scraper.scrape_all_publications()
    scraper.documents.extend(pub_docs)

    documents = scraper.documents
    print(f"\nCollected {len(documents)} documents")

    # Now index with correct model
    print(f"\n INDEXING: {len(documents)} documents to ChromaDB...")

    try:
        # Load embedding model (paraphrase-multilingual-MiniLM-L12-v2 = 384 dimensions)
        print("  Loading embedding model (384-dim)...")
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

        # Connect to ChromaDB
        client = chromadb.PersistentClient(path=CHROMADB_PATH)
        collection = client.get_collection(name=COLLECTION_NAME)

        batch_size = 50
        indexed = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            ids = []
            texts = []
            embeddings = []
            metadatas = []

            for doc in batch:
                # Create embedding text
                embed_text = f"{doc.title}. {doc.text_content[:2000]}"
                embedding = model.encode(embed_text).tolist()

                ids.append(doc.doc_id)
                texts.append(doc.text_content[:5000])
                embeddings.append(embedding)
                metadatas.append(
                    {
                        "title": doc.title[:200],
                        "url": doc.url,
                        "doc_type": doc.doc_type,
                        "source": doc.source,
                        "date": doc.date,
                        "indexed_at": datetime.now().isoformat(),
                    }
                )

            collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

            indexed += len(batch)
            print(f"  Batch {i // batch_size + 1}: {indexed}/{len(documents)} indexed")

        final_count = collection.count()
        print(f"\n SUCCESS: {final_count:,} total documents in collection")

        # Count kemi docs
        kemi_results = collection.get(where={"source": "kemi"})
        kemi_count = len(kemi_results["ids"]) if kemi_results["ids"] else 0
        print(f" KEMI DOCS: {kemi_count} documents from Kemikalieinspektionen")

        # Save final report
        report = {
            "operation": "KEMI_INDEX",
            "timestamp": datetime.now().isoformat(),
            "documents_indexed": indexed,
            "total_kemi_docs": kemi_count,
            "collection_total": final_count,
        }

        report_path = (
            Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI")
            / "KEMI_FINAL_REPORT.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n Report saved: {report_path}")

        return report

    except Exception as e:
        print(f"\n  ChromaDB Error: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    index_from_cache()
