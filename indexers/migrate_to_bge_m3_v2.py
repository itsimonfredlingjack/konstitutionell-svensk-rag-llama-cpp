#!/usr/bin/env python3
import argparse
import sys
import time
from pathlib import Path
from typing import Any

import chromadb
import torch
from sentence_transformers import SentenceTransformer

CHROMADB_PATH = "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"
NEW_EMBEDDING_MODEL = "BAAI/bge-m3"
BATCH_SIZE = 20  # Increased to 20 for better throughput (was 16). Monitor GPU temp!


class ChromaDBMigrator:
    def __init__(self, chromadb_path: str = CHROMADB_PATH, force: bool = False):
        self.chromadb_path = Path(chromadb_path)
        self.force = force
        self.client = chromadb.PersistentClient(path=str(self.chromadb_path))

        print(f"Loading new embedding model: {NEW_EMBEDDING_MODEL}")
        # Auto-detect and use CUDA if available, otherwise fallback to CPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"🚀 Using device: {device}")
        self.new_model = SentenceTransformer(NEW_EMBEDDING_MODEL, device=device)
        self.new_dim = self.new_model.get_sentence_embedding_dimension()
        print(f"New model loaded: {self.new_dim}-dim embeddings")

    def get_collections_to_migrate(self) -> list[str]:
        all_collections = [c.name for c in self.client.list_collections()]
        legacy_patterns = [
            "riksdag_documents",
            "riksdag_documents_p1",
            "swedish_gov_docs",
            "sfs_lagtext",
        ]
        to_migrate = []
        for pattern in legacy_patterns:
            for coll_name in all_collections:
                if coll_name == pattern:
                    to_migrate.append(coll_name)
                    break
        return to_migrate

    def create_new_collection(self, old_name: str) -> str:
        new_name = f"{old_name}_bge_m3_1024"
        try:
            # Get legacy collection count
            old_collection = self.client.get_collection(old_name)
            old_count = old_collection.count()

            # Check if new collection already exists
            try:
                existing = self.client.get_collection(new_name)
                existing_count = existing.count()

                if not self.force:
                    print(f"Collection {new_name} already exists ({existing_count:,} docs)!")
                    print(
                        f"Legacy has {old_count:,} docs. ({existing_count:,}/{old_count:,} migrated)"
                    )
                    print("Use --force to overwrite.")
                    sys.exit(1)

                # Force mode: check migration status
                print("Force mode: Checking migration status...")
                print(f"  Target: {old_count:,} docs (legacy collection)")
                print(f"  Current: {existing_count:,} docs (new collection)")

                if existing_count >= old_count:
                    # Fully migrated - safe to drop and restart
                    print(
                        f"Collection fully migrated ({existing_count:,}/{old_count:,}). Dropping and restarting..."
                    )
                    self.client.delete_collection(new_name)
                    print(f"Dropped existing collection: {new_name}")
                    # Will create new collection below
                    new_collection = None
                else:
                    # Partial migration - RESUME, don't delete!
                    pct = (existing_count / old_count) * 100
                    print(
                        f"Partial migration detected: {existing_count:,}/{old_count:,} ({pct:.1f}%)"
                    )
                    print("🔄 RESUMING migration (keeping existing collection)")
                    # Don't delete, just return the new name
                    # migrate_collection will handle resume
                    return new_name
            except Exception:
                # New collection doesn't exist - create it
                print(f"New collection {new_name} does not exist. Creating...")

            self.client.create_collection(
                name=new_name,
                metadata={
                    "description": f"Migrated from {old_name} with BGE-M3 1024-dim embeddings",
                    "embedding_model": NEW_EMBEDDING_MODEL,
                    "embedding_dimension": self.new_dim,
                    "migration_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            print(f"Created new collection: {new_name}")
            return new_name
        except Exception as e:
            print(f"Failed to create collection {new_name}: {e}")
            raise

    def migrate_collection(self, old_name: str, new_name: str) -> dict[str, Any]:
        print(f"\nMigrating {old_name} -> {new_name}")
        old_collection = self.client.get_collection(old_name)

        # Check if new collection exists for resume
        new_collection_exists = False
        new_collection = None

        try:
            new_collection = self.client.get_collection(new_name)
            new_collection_exists = True
            print(f"Found existing new collection: {new_name}")
        except:
            print(f"Creating new collection: {new_name}")
            new_collection = self.client.create_collection(
                name=new_name,
                metadata={
                    "description": f"Migrated from {old_name} with BGE-M3 1024-dim embeddings",
                    "embedding_model": NEW_EMBEDDING_MODEL,
                    "embedding_dimension": self.new_dim,
                    "migration_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

        total_docs = old_collection.count()
        print(f"Total documents to migrate: {total_docs}")

        if total_docs == 0:
            print(f"Collection {old_name} is empty, skipping")
            return {"migrated": 0, "errors": 0, "skipped": 0}

        # Resume from existing collection if partial migration
        migrated = 0
        if new_collection_exists:
            migrated = new_collection.count()
            pct = (migrated / total_docs) * 100
            print(f"Resuming from offset {migrated} ({pct:.1f}% complete)")
            if migrated >= total_docs:
                print("Collection already fully migrated. Skipping.")
                return {"migrated": migrated, "errors": 0, "skipped": 0}
        else:
            print("Starting from scratch (no existing collection)")
            migrated = 0

        errors = 0
        skipped = 0

        # Start offset from migrated count (resume support)
        offset = migrated

        while offset < total_docs:
            try:
                batch = old_collection.get(
                    limit=BATCH_SIZE, offset=offset, include=["documents", "metadatas"]
                )

                ids = batch.get("ids") or []
                if not ids:
                    break

                batch_size = len(ids)
                print(
                    f"  Processing batch {offset // BATCH_SIZE + 1}: {batch_size} docs (offset {offset})"
                )

                documents = batch.get("documents") or []
                metadatas = batch.get("metadatas") or [{}] * len(ids)

                safe_documents = []
                for doc in documents:
                    if doc is None:
                        safe_documents.append("")
                    elif isinstance(doc, str):
                        safe_documents.append(doc)
                    else:
                        safe_documents.append(str(doc))

                if len(safe_documents) != len(ids):
                    safe_documents = safe_documents[: len(ids)]
                    if len(safe_documents) < len(ids):
                        safe_documents.extend([""] * (len(ids) - len(safe_documents)))

                if len(metadatas) != len(ids):
                    metadatas = list(metadatas[: len(ids)]) if metadatas else []
                    if len(metadatas) < len(ids):
                        metadatas.extend([{}] * (len(ids) - len(metadatas)))

                embeddings = self.new_model.encode(
                    safe_documents,
                    batch_size=min(BATCH_SIZE, len(safe_documents)),
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ).tolist()

                new_collection.add(
                    ids=ids, documents=safe_documents, metadatas=metadatas, embeddings=embeddings
                )

                migrated += batch_size
                offset += batch_size

                if migrated % 1000 == 0 or migrated >= total_docs:
                    pct = (migrated / total_docs) * 100
                    print(f"  Migrated: {migrated}/{total_docs} ({pct:.1f}%)")

            except Exception as e:
                error_msg = str(e)
                print(f"  Error processing batch at offset {offset}: {error_msg}")

                if "CUDA out of memory" in error_msg:
                    print("🚨 CRITICAL: GPU Out of Memory! Stopping immediately to prevent loop.")
                    sys.exit(1)

                import traceback

                traceback.print_exc()
                errors += 1
                offset += BATCH_SIZE
                continue

        return {"migrated": migrated, "errors": errors, "skipped": skipped, "total": total_docs}

    def verify_migration(self, old_name: str, new_name: str) -> dict[str, Any]:
        print(f"\nVerifying migration: {old_name} -> {new_name}")
        old_collection = self.client.get_collection(old_name)
        new_collection = self.client.get_collection(new_name)

        old_count = old_collection.count()
        new_count = new_collection.count()

        print(f"Original collection: {old_count} docs")
        print(f"New collection: {new_count} docs")

        return {
            "old_count": old_count,
            "new_count": new_count,
            "migration_complete": new_count >= old_count,
        }

    def run_migration(self, collections: list[str] | None = None) -> dict[str, Any]:
        if collections is None:
            collections = self.get_collections_to_migrate()

        print(f"Starting migration of {len(collections)} collections:")
        for coll in collections:
            print(f"  - {coll}")

        results = {}

        for old_name in collections:
            try:
                print(f"\n{'=' * 60}")
                print(f"MIGRATING: {old_name}")
                print(f"{'=' * 60}")

                new_name = self.create_new_collection(old_name)
                migration_result = self.migrate_collection(old_name, new_name)
                verification = self.verify_migration(old_name, new_name)

                results[old_name] = {
                    "new_collection": new_name,
                    "migration": migration_result,
                    "verification": verification,
                }

                print(f"Migration completed for {old_name}")

            except Exception as e:
                print(f"Migration failed for {old_name}: {e}")
                import traceback

                traceback.print_exc()
                results[old_name] = {"error": str(e)}

        return results

    def print_summary(self, results: dict[str, Any]):
        print(f"\n{'=' * 80}")
        print("MIGRATION SUMMARY")
        print(f"{'=' * 80}")

        total_migrated = 0
        total_errors = 0
        successful = 0

        for old_name, result in results.items():
            if "error" in result:
                print(f"ERROR {old_name}: {result['error']}")
                continue

            migration = result["migration"]
            verification = result["verification"]

            print(f"{old_name} -> {result['new_collection']}")
            print(f"  Migrated: {migration['migrated']}/{migration['total']} docs")
            print(f"  Errors: {migration['errors']}")
            print(f"  Skipped: {migration['skipped']}")
            print(f"  Verified: {'OK' if verification['migration_complete'] else 'FAIL'}")

            total_migrated += migration["migrated"]
            total_errors += migration["errors"]
            if verification["migration_complete"]:
                successful += 1

        print("\nTOTALS:")
        print(f"  Collections processed: {len(results)}")
        print(f"  Successful migrations: {successful}")
        print(f"  Total documents migrated: {total_migrated}")
        print(f"  Total errors: {total_errors}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ChromaDB collections from KBLab 768-dim to BGE-M3 1024-dim"
    )
    parser.add_argument("--collections", nargs="+", help="Specific collections to migrate")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be migrated without doing it"
    )
    parser.add_argument(
        "--chromadb-path", default=CHROMADB_PATH, help="Path to ChromaDB data directory"
    )
    parser.add_argument("--force", action="store_true", help="Force overwrite existing collections")

    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN - Showing collections that would be migrated")
        client = chromadb.PersistentClient(path=args.chromadb_path)
        collections = [c.name for c in client.list_collections()]

        legacy_patterns = [
            "riksdag_documents",
            "riksdag_documents_p1",
            "swedish_gov_docs",
            "sfs_lagtext",
        ]
        to_migrate = []

        for pattern in legacy_patterns:
            for coll_name in collections:
                if coll_name == pattern:
                    old_count = client.get_collection(coll_name).count()
                    new_name = f"{coll_name}_bge_m3_1024"
                    to_migrate.append((coll_name, old_count, new_name))
                    break

        print(f"\nCollections to migrate ({len(to_migrate)}):")
        for old_name, count, new_name in to_migrate:
            print(f"  {old_name} ({count:,} docs) -> {new_name}")
        return

    try:
        migrator = ChromaDBMigrator(args.chromadb_path, force=args.force)
        results = migrator.run_migration(args.collections)
        migrator.print_summary(results)

        if any("error" in result for result in results.values()):
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
