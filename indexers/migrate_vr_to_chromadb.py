#!/usr/bin/env python3
"""
Migrate Vetenskapsrådet data from SQLite to ChromaDB
Run this when ChromaDB segfault is fixed
"""

import sqlite3


def migrate_sqlite_to_chromadb(db_path: str, chromadb_path: str):
    """Migrate from SQLite to ChromaDB"""

    # ChromaDB import (skip if broken)
    try:
        import chromadb
    except ImportError:
        print("ChromaDB not available")
        return

    # Connect to SQLite
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM documents")

    # Setup ChromaDB
    client = chromadb.PersistentClient(path=chromadb_path)

    try:
        collection = client.get_collection("swedish_gov_docs")
    except Exception:
        collection = client.create_collection(
            name="swedish_gov_docs", metadata={"description": "Swedish government documents"}
        )

    # Migrate in batches
    batch_size = 100
    ids = []
    documents = []
    metadatas = []

    total = 0

    for row in cursor.fetchall():
        doc_id = row[0]
        source = row[1]
        url = row[2]
        title = row[3]
        content = row[4]
        published_date = row[5]
        pdf_links = row[6]
        scraped_at = row[7]

        # Metadata
        metadata = {
            "source": source,
            "url": url,
            "title": title[:500] if title else "",
            "scraped_at": scraped_at,
        }

        if published_date:
            metadata["published_date"] = published_date

        if pdf_links:
            metadata["pdf_links"] = pdf_links

        # Limit content
        content_limited = content[:10000] if content else ""

        ids.append(doc_id)
        documents.append(content_limited)
        metadatas.append(metadata)

        # Save batch
        if len(ids) >= batch_size:
            collection.add(ids=ids, documents=documents, metadatas=metadatas)
            print(f"Migrated {len(ids)} documents")
            total += len(ids)
            ids = []
            documents = []
            metadatas = []

    # Save remaining
    if ids:
        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        total += len(ids)
        print(f"Migrated {len(ids)} documents")

    conn.close()

    print(f"\nTotal migrated: {total}")
    return total


if __name__ == "__main__":
    db_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/vetenskapsradet.db"
    chromadb_path = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"

    print("=" * 60)
    print("MIGRATE VETENSKAPSRÅDET TO CHROMADB")
    print("=" * 60)

    try:
        total = migrate_sqlite_to_chromadb(db_path, chromadb_path)
        print(f"\n✅ Migration complete: {total} documents")
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\nData is safe in SQLite and JSON exports")
