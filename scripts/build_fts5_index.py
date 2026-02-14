#!/usr/bin/env python3
"""
Build FTS5 Index from docs.jsonl
=================================

Streams data/bm25_index/docs.jsonl into a SQLite FTS5 database at data/bm25_fts5/bm25.db.
Each JSONL line: {"id": "...", "text": "..."}

Usage:
    cd /home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI
    python scripts/build_fts5_index.py
"""

import json
import sqlite3
import sys
import time
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
JSONL_PATH = PROJECT_DIR / "data" / "bm25_index" / "docs.jsonl"
OUTPUT_DIR = PROJECT_DIR / "data" / "bm25_fts5"
DB_PATH = OUTPUT_DIR / "bm25.db"

BATCH_SIZE = 5000


def build_fts5_index():
    if not JSONL_PATH.exists():
        print(f"ERROR: Source file not found: {JSONL_PATH}")
        sys.exit(1)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Remove existing DB if present
    if DB_PATH.exists():
        print(f"Removing existing DB: {DB_PATH}")
        DB_PATH.unlink()

    print(f"Source: {JSONL_PATH} ({JSONL_PATH.stat().st_size / 1e9:.2f} GB)")
    print(f"Output: {DB_PATH}")
    print(f"Batch size: {BATCH_SIZE}")
    print()

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-65536")  # 64MB cache

    # Create FTS5 virtual table
    conn.execute("""
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            doc_id UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2',
            detail='column'
        )
    """)

    start = time.perf_counter()
    doc_count = 0
    batch = []
    errors = 0

    with open(JSONL_PATH, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                doc_id = obj["id"]
                text = obj["text"]
                batch.append((doc_id, text))
                doc_count += 1
            except (json.JSONDecodeError, KeyError) as e:
                errors += 1
                if errors <= 5:
                    print(f"  WARNING: Line {line_num}: {e}")
                continue

            if len(batch) >= BATCH_SIZE:
                conn.executemany("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", batch)
                conn.commit()
                elapsed = time.perf_counter() - start
                rate = doc_count / elapsed if elapsed > 0 else 0
                print(
                    f"  Inserted {doc_count:>10,} docs ({elapsed:>6.1f}s, {rate:>8,.0f} docs/s)",
                    end="\r",
                )
                batch = []

    # Insert remaining
    if batch:
        conn.executemany("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", batch)
        conn.commit()

    elapsed_insert = time.perf_counter() - start
    print(f"\n  Insert complete: {doc_count:,} docs in {elapsed_insert:.1f}s")

    if errors:
        print(f"  Skipped {errors} malformed lines")

    # Optimize FTS5 index (merge segments)
    print("  Optimizing FTS5 index...")
    opt_start = time.perf_counter()
    conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('optimize')")
    conn.commit()
    opt_time = time.perf_counter() - opt_start
    print(f"  Optimize complete in {opt_time:.1f}s")

    conn.close()

    total_time = time.perf_counter() - start
    db_size_mb = DB_PATH.stat().st_size / 1e6
    db_size_gb = db_size_mb / 1000

    print()
    print("=" * 50)
    print(f"  Documents indexed: {doc_count:,}")
    print(f"  Database size:     {db_size_mb:,.1f} MB ({db_size_gb:.2f} GB)")
    print(f"  Total time:        {total_time:.1f}s ({total_time / 60:.1f} min)")
    print(f"  Output:            {DB_PATH}")
    print("=" * 50)


if __name__ == "__main__":
    build_fts5_index()
