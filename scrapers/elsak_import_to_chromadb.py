#!/usr/bin/env python3
"""
Import Elsäkerhetsverket documents to ChromaDB
==============================================
Läser från: /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/elsak_harvest.json
Skriver till: swedish_gov_docs collection
"""

import json
import sys
from datetime import datetime

# Importera ChromaDB med felhantering
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("ERROR: chromadb inte installerad. Kör: pip install chromadb")
    sys.exit(1)

DATA_FILE = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/elsak_harvest.json"
CHROMA_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
COLLECTION_NAME = "swedish_gov_docs"


def import_to_chromadb():
    """Importera Elsäkerhetsverket-dokument till ChromaDB"""

    # Ladda JSON-data
    print(f"Läser från: {DATA_FILE}")
    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)

    documents = data["documents"]
    print(f"Hittade {len(documents)} dokument att importera")

    # Anslut till ChromaDB
    print(f"Ansluter till ChromaDB: {CHROMA_PATH}")
    client = chromadb.PersistentClient(
        path=CHROMA_PATH, settings=Settings(allow_reset=True, anonymized_telemetry=False)
    )

    # Hämta eller skapa collection
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        print(f"Använder befintlig collection: {COLLECTION_NAME}")
        existing_count = collection.count()
        print(f"  Befintliga dokument: {existing_count}")
    except Exception:
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Swedish government documents for constitutional AI research"},
        )
        print(f"Skapade ny collection: {COLLECTION_NAME}")

    # Förbered batch-import
    ids = []
    metadatas = []
    documents_texts = []

    for idx, doc in enumerate(documents):
        # Skapa unikt ID
        doc_id = f"elsak_{idx}_{hash(doc['url']) % 1000000}"

        # Extrahera innehåll (använd title om ingen content finns)
        content = doc.get("content", "")
        if not content or len(content) < 50:
            content = f"{doc['title']}\n\nDokument från Elsäkerhetsverket.\nURL: {doc['url']}"

        # Metadata
        metadata = {
            "source": "elsakerhetsverket",
            "title": doc["title"],
            "url": doc["url"],
            "type": doc["type"],
            "format": doc.get("format", "unknown"),
            "scraped_at": doc.get("scraped_at", datetime.now().isoformat()),
            "agency": "Elsäkerhetsverket",
            "domain": "elsäkerhet",
        }

        ids.append(doc_id)
        metadatas.append(metadata)
        documents_texts.append(content)

    # Batch-import
    print(f"\nImporterar {len(ids)} dokument till ChromaDB...")
    batch_size = 100

    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_metadatas = metadatas[i : i + batch_size]
        batch_documents = documents_texts[i : i + batch_size]

        collection.add(ids=batch_ids, metadatas=batch_metadatas, documents=batch_documents)

        print(f"  Importerade batch {i // batch_size + 1}: {len(batch_ids)} dokument")

    # Verifiera import
    final_count = collection.count()
    print("\nKLART!")
    print(f"Total antal dokument i collection: {final_count}")

    # Testa sökning
    print("\nTestar sökning efter 'ELSÄK-FS'...")
    results = collection.query(
        query_texts=["ELSÄK-FS föreskrifter"], n_results=3, where={"source": "elsakerhetsverket"}
    )

    if results["documents"][0]:
        print(f"Hittade {len(results['documents'][0])} resultat:")
        for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
            print(f"  {i + 1}. {meta['title'][:60]}")

    return final_count


if __name__ == "__main__":
    try:
        count = import_to_chromadb()
        print(f"\n✓ Import lyckades: {count} dokument i ChromaDB")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Import misslyckades: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
