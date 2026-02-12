#!/usr/bin/env python3
"""
Build BM25 Index from ChromaDB Collections
===========================================

One-time script to extract documents from ChromaDB and build a retriv BM25 index.
This creates the sidecar index used for hybrid search.

Usage:
    python scripts/build_bm25_index.py

Output:
    data/bm25_index/ - retriv index directory (~1-3 GB for 1.3M docs)

Expected runtime: 30-60 minutes for 1.3M documents
"""

import gc
import re
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import chromadb
import retriv

# Import compound splitter (after path setup)
from app.services.swedish_compound_splitter import get_compound_splitter

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# ChromaDB path
CHROMADB_PATH = Path(__file__).parent.parent / "chromadb_data"

# Output index path
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "bm25_index"

# Collections to index (Jina v3 1024-dim collections)
COLLECTIONS_TO_INDEX = [
    "sfs_lagtext_jina_v3_1024",
    "riksdag_documents_p1_jina_v3_1024",
    "swedish_gov_docs_jina_v3_1024",
    "diva_research_jina_v3_1024",
]

# Batch size for ChromaDB extraction
BATCH_SIZE = 5000

# retriv settings
RETRIV_SETTINGS = {
    "index_name": str(OUTPUT_PATH),  # retriv uses index_name as save path
    "model": "bm25",
    "min_df": 1,
    "tokenizer": "whitespace",  # Will use Swedish Snowball stemmer
    "stemmer": "swedish",
    "stopwords": "swedish",
    "do_lowercasing": True,
    "do_ampersand_normalization": True,
    "do_special_chars_normalization": True,
}


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def log(msg: str):
    """Print timestamped log message."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


def expand_compounds(text: str, splitter) -> str:
    """
    Expand compound words in text for BM25 indexing.

    Adds component words after each compound:
    "Trafikskadelagen reglerar" → "Trafikskadelagen trafik skade lag reglerar"

    This ensures:
    - Exact match still works (original word preserved)
    - Partial matches work (components indexed)
    """
    if not text:
        return text

    words = re.findall(r"\b\w+\b", text)
    result_parts = []

    for word in words:
        parts = splitter.split(word)
        result_parts.extend(parts)

    return " ".join(result_parts)


def extract_documents_from_chromadb(
    client: chromadb.PersistentClient,
    collection_name: str,
) -> list:
    """
    Extract all documents from a ChromaDB collection.

    Returns list of dicts with keys: id, text
    """
    try:
        collection = client.get_collection(collection_name)
        total = collection.count()

        if total == 0:
            log(f"  {collection_name}: Empty collection, skipping")
            return []

        log(f"  {collection_name}: Extracting {format_number(total)} documents...")

        documents = []
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

                # Combine text with metadata for richer indexing
                title = metadata.get("title", "")
                combined_text = f"{title} {text}".strip() if title else text

                if combined_text:
                    documents.append(
                        {
                            "id": doc_id,
                            "text": combined_text,
                        }
                    )

            offset += BATCH_SIZE

            # Progress update every 50k docs
            if offset % 50000 == 0:
                log(f"    Progress: {format_number(offset)}/{format_number(total)}")

        log(f"  {collection_name}: Extracted {format_number(len(documents))} documents")
        return documents

    except Exception as e:
        log(f"  {collection_name}: Error - {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


def main():
    """Build BM25 index from ChromaDB collections."""
    log("=" * 60)
    log("BM25 Index Builder")
    log("=" * 60)

    start_time = time.time()

    # Verify ChromaDB exists
    if not CHROMADB_PATH.exists():
        log(f"ERROR: ChromaDB not found at {CHROMADB_PATH}")
        sys.exit(1)

    # Create output directory
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Connect to ChromaDB
    log(f"Connecting to ChromaDB at {CHROMADB_PATH}")
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))

    # List available collections
    available_collections = [c.name for c in client.list_collections()]
    log(f"Available collections: {len(available_collections)}")

    # Filter to collections we want to index
    collections_to_process = [c for c in COLLECTIONS_TO_INDEX if c in available_collections]
    log(f"Collections to index: {collections_to_process}")

    if not collections_to_process:
        log("ERROR: No matching collections found")
        sys.exit(1)

    # Initialize compound splitter
    log("\nInitializing Swedish compound splitter...")
    splitter = get_compound_splitter()
    if splitter.is_available():
        stats = splitter.get_stats()
        log(f"  Compound splitter ready: {stats['word_count']:,} words in dictionary")
    else:
        log("  WARNING: Compound splitter not available, indexing without expansion")
        splitter = None

    # Extract documents from all collections
    log("\nPhase 1: Extracting documents from ChromaDB")
    all_documents = []

    for collection_name in collections_to_process:
        docs = extract_documents_from_chromadb(client, collection_name)
        all_documents.extend(docs)

        # Free memory
        gc.collect()

    log(f"\nTotal documents extracted: {format_number(len(all_documents))}")

    if not all_documents:
        log("ERROR: No documents extracted")
        sys.exit(1)

    # Phase 1.5: Expand compounds in document text (for Swedish legal terms)
    if splitter:
        log("\nPhase 1.5: Expanding Swedish compound words")
        expand_start = time.time()
        expanded_count = 0

        for i, doc in enumerate(all_documents):
            original_text = doc["text"]
            expanded_text = expand_compounds(original_text, splitter)

            # Only update if expansion added something
            if len(expanded_text) > len(original_text):
                doc["text"] = expanded_text
                expanded_count += 1

            # Progress every 100k docs
            if (i + 1) % 100000 == 0:
                log(f"    Progress: {format_number(i + 1)}/{format_number(len(all_documents))}")

        expand_time = time.time() - expand_start
        log(
            f"  Compound expansion complete: {expanded_count:,} docs expanded in {expand_time:.1f}s"
        )
        gc.collect()

    # Build retriv index
    log("\nPhase 2: Building BM25 index with retriv")
    log(f"  Settings: {RETRIV_SETTINGS}")

    try:
        # Create sparse retriever
        sr = retriv.SparseRetriever(
            index_name=RETRIV_SETTINGS["index_name"],
            model=RETRIV_SETTINGS["model"],
            min_df=RETRIV_SETTINGS["min_df"],
            tokenizer=RETRIV_SETTINGS["tokenizer"],
            stemmer=RETRIV_SETTINGS["stemmer"],
            stopwords=RETRIV_SETTINGS["stopwords"],
            do_lowercasing=RETRIV_SETTINGS["do_lowercasing"],
            do_ampersand_normalization=RETRIV_SETTINGS["do_ampersand_normalization"],
            do_special_chars_normalization=RETRIV_SETTINGS["do_special_chars_normalization"],
        )

        # Index documents
        log("  Indexing documents (this may take a while)...")
        index_start = time.time()

        sr = sr.index(
            collection=all_documents,
            show_progress=True,
        )

        index_time = time.time() - index_start
        log(f"  Indexing completed in {index_time:.1f}s")

        # Save index (retriv auto-saves to index_name path)
        log(f"\nPhase 3: Saving index to {OUTPUT_PATH}")
        sr.save()
        log("  Index saved successfully")

        # Get index size
        index_size_mb = sum(f.stat().st_size for f in OUTPUT_PATH.rglob("*") if f.is_file()) / (
            1024 * 1024
        )
        log(f"  Index size: {index_size_mb:.1f} MB")

    except Exception as e:
        log(f"ERROR: Failed to build index - {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    # Summary
    total_time = time.time() - start_time
    log("\n" + "=" * 60)
    log("BUILD COMPLETE")
    log("=" * 60)
    log(f"  Documents indexed: {format_number(len(all_documents))}")
    log(f"  Index location: {OUTPUT_PATH}")
    log(f"  Index size: {index_size_mb:.1f} MB")
    log(f"  Total time: {total_time / 60:.1f} minutes")
    log("")
    log("To use the index, ensure the backend service is restarted.")
    log("The BM25Service will automatically load this index on first search.")


if __name__ == "__main__":
    main()
