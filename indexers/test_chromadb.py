#!/usr/bin/env python3
print("Step 1: Importing chromadb...")
import chromadb

print("Step 2: Creating client...")
client = chromadb.PersistentClient(
    path="/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
)
print("Step 3: Getting collection...")
collection = client.get_or_create_collection(name="swedish_gov_docs")
print("Step 4: Counting documents...")
count = collection.count()
print(f"SUCCESS: Collection has {count} documents")
