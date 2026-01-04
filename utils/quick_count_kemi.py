#!/usr/bin/env python3
"""Quick count of existing kemi documents in ChromaDB"""

import chromadb

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

try:
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    collection = client.get_collection("swedish_gov_docs")

    # Get all kemi documents
    results = collection.get(where={"source": "kemi"})
    count = len(results["ids"]) if results["ids"] else 0

    print(f"Current kemi docs in ChromaDB: {count}")

    if count > 0:
        print("\nSample documents:")
        for i in range(min(3, count)):
            print(f"  - {results['metadatas'][i].get('title', 'No title')}")

except Exception as e:
    print(f"Error: {e}")
    print("Likely no kemi documents yet.")
