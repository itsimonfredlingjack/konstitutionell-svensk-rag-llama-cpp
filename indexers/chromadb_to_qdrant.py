#!/usr/bin/env python3
"""
chromadb_to_qdrant.py - Direct copy from ChromaDB to Qdrant (no re-embedding)

SOURCE: chromadb_data/ (535,024 docs, 768 dim embeddings)
TARGET: Qdrant localhost:6333, collection "documents"

Usage:
    python chromadb_to_qdrant.py                    # Full migration
    python chromadb_to_qdrant.py --collection riksdag_documents_p1
    python chromadb_to_qdrant.py --dry-run          # Count only
    python chromadb_to_qdrant.py --reset            # Delete and recreate collection
"""

import argparse
import hashlib
import time
from pathlib import Path

import chromadb
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

# Configuration
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
TARGET_COLLECTION = "documents"
VECTOR_DIM = 768
BATCH_SIZE = 1000
PROGRESS_INTERVAL = 10000


def get_chromadb_client() -> chromadb.PersistentClient:
    """Initialize ChromaDB client."""
    return chromadb.PersistentClient(path=str(CHROMADB_PATH))


def get_qdrant_client() -> QdrantClient:
    """Initialize Qdrant client."""
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection(qdrant: QdrantClient, reset: bool = False) -> None:
    """Ensure target collection exists with correct config."""
    collections = [c.name for c in qdrant.get_collections().collections]

    if reset and TARGET_COLLECTION in collections:
        print(f"Deleting existing collection '{TARGET_COLLECTION}'...")
        qdrant.delete_collection(TARGET_COLLECTION)
        collections.remove(TARGET_COLLECTION)

    if TARGET_COLLECTION not in collections:
        print(f"Creating collection '{TARGET_COLLECTION}' (dim={VECTOR_DIM})...")
        qdrant.create_collection(
            collection_name=TARGET_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
    else:
        # Verify dimension
        info = qdrant.get_collection(TARGET_COLLECTION)
        if info.config.params.vectors.size != VECTOR_DIM:
            print(
                f"WARNING: Collection has dim {info.config.params.vectors.size}, expected {VECTOR_DIM}"
            )


def generate_point_id(source: str, doc_id: str) -> str:
    """Generate deterministic point ID from source and doc_id."""
    combined = f"{source}:{doc_id}"
    return hashlib.md5(combined.encode()).hexdigest()


def check_existing_ids(qdrant: QdrantClient, ids: list[str]) -> set:
    """Check which IDs already exist in Qdrant."""
    try:
        result = qdrant.retrieve(
            collection_name=TARGET_COLLECTION, ids=ids, with_payload=False, with_vectors=False
        )
        return {p.id for p in result}
    except Exception:
        return set()


def migrate_collection(
    chromadb_path: Path,
    qdrant: QdrantClient,
    collection_name: str,
    dry_run: bool = False,
    skip_existing: bool = True,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Migrate a single ChromaDB collection to Qdrant.

    Uses ID-based fetching instead of offset to avoid ChromaDB internal errors.
    """

    # Create fresh client for each collection to avoid state issues
    chroma_client = chromadb.PersistentClient(path=str(chromadb_path))
    collection = chroma_client.get_collection(collection_name)
    total = collection.count()

    print(f"\n{'='*60}")
    print(f"Collection: {collection_name}")
    print(f"Total documents: {total:,}")
    print(f"{'='*60}")

    if total == 0:
        return {"total": 0, "migrated": 0, "skipped": 0, "errors": 0}

    if dry_run:
        print("[DRY RUN] Would migrate documents")
        return {"total": total, "migrated": 0, "skipped": 0, "errors": 0}

    # Step 1: Get ALL IDs first (without embeddings - much faster and more reliable)
    print("  Fetching all document IDs...")
    all_ids = []
    id_offset = 0
    id_batch_size = 50000  # Large batches for ID-only fetch

    while id_offset < total:
        try:
            id_results = collection.get(
                limit=id_batch_size,
                offset=id_offset,
                include=[],  # Only IDs, no embeddings/documents
            )
            if not id_results or not id_results["ids"]:
                break
            all_ids.extend(id_results["ids"])
            id_offset += len(id_results["ids"])
            if id_offset % 100000 == 0:
                print(f"    ... {id_offset:,} IDs fetched")
        except Exception as e:
            print(f"  Warning: ID fetch failed at offset {id_offset}, trying smaller batches: {e}")
            # Fallback to smaller batches
            id_batch_size = 10000
            continue

    print(f"  Total IDs: {len(all_ids):,}")

    if len(all_ids) == 0:
        print("  ERROR: Could not fetch any IDs")
        return {"total": total, "migrated": 0, "skipped": 0, "errors": total}

    stats = {"total": total, "migrated": 0, "skipped": 0, "errors": 0}
    start_time = time.time()

    # Step 2: Fetch documents in batches BY ID
    for batch_start in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[batch_start : batch_start + batch_size]

        # Fetch batch from ChromaDB by ID with retry
        results = None
        for retry in range(3):
            try:
                results = collection.get(
                    ids=batch_ids, include=["embeddings", "documents", "metadatas"]
                )
                break
            except Exception as e:
                if retry < 2:
                    print(f"  Retry {retry+1} at batch {batch_start}: {e}")
                    time.sleep(1)
                else:
                    print(
                        f"  ERROR: Failed batch at {batch_start}, skipping {len(batch_ids)} docs: {e}"
                    )
                    stats["errors"] += len(batch_ids)
                    continue

        if not results or not results["ids"]:
            stats["errors"] += len(batch_ids)
            continue

        # Prepare points for Qdrant
        points = []
        point_ids = []

        for i, doc_id in enumerate(results["ids"]):
            # Generate deterministic ID
            point_id = generate_point_id(collection_name, doc_id)
            point_ids.append(point_id)

            # Get embedding
            embeddings = results.get("embeddings")
            if embeddings is None or len(embeddings) <= i:
                stats["errors"] += 1
                continue
            embedding = embeddings[i]
            if embedding is None or (hasattr(embedding, "__len__") and len(embedding) == 0):
                stats["errors"] += 1
                continue

            # Get document text
            documents = results.get("documents")
            document = documents[i] if documents is not None and len(documents) > i else ""

            # Get metadata
            metadatas = results.get("metadatas")
            metadata = metadatas[i] if metadatas is not None and len(metadatas) > i else {}

            # Build payload
            payload = {
                "text": document,
                "source": collection_name,
                "original_id": doc_id,
                **{k: v for k, v in metadata.items() if v is not None},
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=list(embedding) if hasattr(embedding, "tolist") else embedding,
                    payload=payload,
                )
            )

        # Check for existing IDs if skip_existing is enabled
        if skip_existing and points:
            existing_ids = check_existing_ids(qdrant, point_ids)
            if existing_ids:
                points = [p for p in points if p.id not in existing_ids]
                stats["skipped"] += len(existing_ids)

        # Upsert to Qdrant
        if points:
            try:
                qdrant.upsert(collection_name=TARGET_COLLECTION, points=points, wait=True)
                stats["migrated"] += len(points)
            except Exception as e:
                print(f"  ERROR at batch {batch_start}: {e}")
                stats["errors"] += len(points)

        # Progress report
        processed = stats["migrated"] + stats["skipped"] + stats["errors"]
        if processed % PROGRESS_INTERVAL < batch_size or batch_start + batch_size >= len(all_ids):
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = len(all_ids) - batch_start - batch_size
            eta = remaining / rate if rate > 0 else 0
            print(
                f"  Progress: {batch_start + len(batch_ids):,}/{len(all_ids):,} ({(batch_start + len(batch_ids))*100/len(all_ids):.1f}%) "
                f"| Migrated: {stats['migrated']:,} | Skipped: {stats['skipped']:,} "
                f"| Rate: {rate:.0f}/s | ETA: {eta:.0f}s"
            )

    elapsed = time.time() - start_time
    print(f"\nCompleted in {elapsed:.1f}s")
    print(f"  Migrated: {stats['migrated']:,}")
    print(f"  Skipped:  {stats['skipped']:,}")
    print(f"  Errors:   {stats['errors']:,}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate ChromaDB to Qdrant")
    parser.add_argument("--collection", "-c", help="Specific collection to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't migrate")
    parser.add_argument(
        "--reset", action="store_true", help="Delete and recreate Qdrant collection"
    )
    parser.add_argument("--no-skip", action="store_true", help="Don't skip existing documents")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size (default: 1000)")
    args = parser.parse_args()

    batch_size = args.batch_size

    print("=" * 60)
    print("CHROMADB TO QDRANT MIGRATION")
    print("=" * 60)
    print(f"Source: {CHROMADB_PATH}")
    print(f"Target: {QDRANT_HOST}:{QDRANT_PORT}/{TARGET_COLLECTION}")
    print(f"Batch size: {batch_size}")
    print(f"Skip existing: {not args.no_skip}")

    # Initialize clients
    chroma = get_chromadb_client()
    qdrant = get_qdrant_client()

    # Ensure collection exists
    if not args.dry_run:
        ensure_collection(qdrant, reset=args.reset)

    # Get collections to migrate
    if args.collection:
        collections = [args.collection]
    else:
        collections = [c.name for c in chroma.list_collections()]
        # Sort by size (largest first for better progress visibility)
        collections.sort(key=lambda c: chroma.get_collection(c).count(), reverse=True)

    print(f"\nCollections to migrate: {len(collections)}")
    for c in collections:
        count = chroma.get_collection(c).count()
        print(f"  - {c}: {count:,}")

    # Migrate each collection
    total_stats = {"total": 0, "migrated": 0, "skipped": 0, "errors": 0}
    start_time = time.time()

    for collection_name in collections:
        stats = migrate_collection(
            CHROMADB_PATH,
            qdrant,
            collection_name,
            dry_run=args.dry_run,
            skip_existing=not args.no_skip,
            batch_size=batch_size,
        )
        for k in total_stats:
            total_stats[k] += stats[k]

    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"Total documents: {total_stats['total']:,}")
    print(f"  Migrated: {total_stats['migrated']:,}")
    print(f"  Skipped:  {total_stats['skipped']:,}")
    print(f"  Errors:   {total_stats['errors']:,}")

    # Verify Qdrant count
    if not args.dry_run:
        info = qdrant.get_collection(TARGET_COLLECTION)
        print(f"\nQdrant '{TARGET_COLLECTION}' now has: {info.points_count:,} points")


if __name__ == "__main__":
    main()
