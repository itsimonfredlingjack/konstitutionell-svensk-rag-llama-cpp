#!/usr/bin/env python3
"""Simple ChromaDB insertion - minimal dependencies"""

import json

# Load data first (before any chromadb import)
print("Loading JSON data...")
with open(
    "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/prv_scrape_20251207_210724.json"
) as f:
    data = json.load(f)

documents = data.get("documents", [])
print(f"Loaded {len(documents)} documents from JSON")

if not documents:
    print("No documents to insert!")
    exit(0)

# Now import chromadb
print("Importing ChromaDB...")
try:
    import chromadb

    print(f"ChromaDB version: {chromadb.__version__}")
except Exception as e:
    print(f"Failed to import ChromaDB: {e}")
    exit(1)

# Connect
CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
print(f"Connecting to: {CHROMADB_PATH}")

try:
    client = chromadb.PersistentClient(path=CHROMADB_PATH)
    print("Client created")
except Exception as e:
    print(f"Failed to create client: {e}")
    exit(1)

try:
    collection = client.get_or_create_collection("swedish_gov_docs")
    print(f"Collection obtained, current count: {collection.count()}")
except Exception as e:
    print(f"Failed to get collection: {e}")
    exit(1)

# Prepare data
print("Preparing documents...")
ids = []
contents = []
metadatas = []

for doc in documents:
    if "id" in doc and "content" in doc:
        ids.append(doc["id"])
        contents.append(doc["content"][:10000])  # Limit content size

        # Metadata
        meta = {}
        for k, v in doc.items():
            if k not in ["id", "content"]:
                # Convert all values to strings
                meta[k] = str(v) if v is not None else ""
        metadatas.append(meta)

print(f"Prepared {len(ids)} documents for insertion")

# Insert in small batches to avoid issues
BATCH_SIZE = 20
total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE

print(f"Inserting in {total_batches} batches of {BATCH_SIZE}...")

for i in range(0, len(ids), BATCH_SIZE):
    batch_num = i // BATCH_SIZE + 1
    end_idx = min(i + BATCH_SIZE, len(ids))

    try:
        collection.upsert(
            ids=ids[i:end_idx], documents=contents[i:end_idx], metadatas=metadatas[i:end_idx]
        )
        print(f"  Batch {batch_num}/{total_batches} inserted ({end_idx}/{len(ids)} docs)")
    except Exception as e:
        print(f"  ERROR in batch {batch_num}: {e}")
        continue

try:
    final_count = collection.count()
    print("\n✅ Insertion complete!")
    print(f"Total documents in collection: {final_count}")

    # Save result
    result = {
        "status": "success",
        "inserted": len(ids),
        "total_in_collection": final_count,
        "source": "prv",
    }

    with open(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/prv_insertion_result.json", "w"
    ) as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

except Exception as e:
    print(f"ERROR getting final count: {e}")
