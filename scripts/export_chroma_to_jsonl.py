#!/usr/bin/env python3
"""
Export ChromaDB Collections to JSONL for FTS5 Index Rebuild
============================================================

Extracts all documents from ChromaDB collections and writes them to
data/bm25_index/docs.jsonl in the format expected by build_fts5_index.py.

Each line: {"id": "doc_id", "text": "title text"}

Usage:
    python scripts/export_chroma_to_jsonl.py
    python scripts/export_chroma_to_jsonl.py --output data/bm25_index/docs.jsonl
"""

import json
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
CHROMADB_PATH = PROJECT_DIR / "chromadb_data"
OUTPUT_PATH = PROJECT_DIR / "data" / "bm25_index" / "docs.jsonl"

# Collections to export
COLLECTIONS = [
    "sfs_lagtext_jina_v3_1024",
    "riksdag_documents_p1_jina_v3_1024",
    "swedish_gov_docs_jina_v3_1024",
    "diva_research_jina_v3_1024",
]

BATCH_SIZE = 5000


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def export_collection(collection, outfile) -> int:
    """Export a single collection to JSONL, returns doc count."""
    total = collection.count()
    if total == 0:
        log(f"  {collection.name}: empty, skipping")
        return 0

    log(f"  {collection.name}: exporting {total:,} documents...")
    exported = 0
    offset = 0

    while offset < total:
        batch = collection.get(
            limit=BATCH_SIZE,
            offset=offset,
            include=["documents", "metadatas"],
        )

        for i, doc_id in enumerate(batch["ids"]):
            text = batch["documents"][i] if batch["documents"] else ""
            metadata = batch["metadatas"][i] if batch["metadatas"] else {}

            title = metadata.get("title", "")
            combined_text = f"{title} {text}".strip() if title else text

            if combined_text:
                line = json.dumps({"id": doc_id, "text": combined_text}, ensure_ascii=False)
                outfile.write(line + "\n")
                exported += 1

        offset += BATCH_SIZE

        if offset % 50000 == 0:
            log(f"    Progress: {offset:,}/{total:,}")

    log(f"  {collection.name}: exported {exported:,} documents")
    return exported


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Export ChromaDB to JSONL for FTS5")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="Output JSONL path")
    parser.add_argument(
        "--chromadb", type=str, default=str(CHROMADB_PATH), help="ChromaDB data path"
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log("=" * 60)
    log("ChromaDB → JSONL Export")
    log("=" * 60)

    start = time.perf_counter()

    log(f"Connecting to ChromaDB: {args.chromadb}")
    client = chromadb.PersistentClient(
        path=args.chromadb, settings=Settings(anonymized_telemetry=False)
    )

    total_exported = 0

    with open(output_path, "w", encoding="utf-8") as outfile:
        for collection_name in COLLECTIONS:
            try:
                collection = client.get_collection(collection_name)
            except Exception as e:
                log(f"  {collection_name}: not found ({e}), skipping")
                continue

            count = export_collection(collection, outfile)
            total_exported += count

    elapsed = time.perf_counter() - start
    file_size_gb = output_path.stat().st_size / 1e9

    log("")
    log("=" * 60)
    log(f"  Total exported: {total_exported:,} documents")
    log(f"  Output file:    {output_path} ({file_size_gb:.2f} GB)")
    log(f"  Time:           {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    log("=" * 60)


if __name__ == "__main__":
    main()
