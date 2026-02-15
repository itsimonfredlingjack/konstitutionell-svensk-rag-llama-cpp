#!/usr/bin/env python3
"""
Build Parent Store — SQLite parent-child store for SFS kapitel-level context
============================================================================

Reads all scraped_data/sfs/*.json files, groups chunks by kapitel, and creates
a SQLite DB for parent-child retrieval. The LLM gets kapitel-level text (parent)
when individual §-level chunks (children) match during vector search.

Usage:
    python scripts/build_parent_store.py
    python scripts/build_parent_store.py --input scrapers/scraped_data/sfs
    python scripts/build_parent_store.py --output data/parent_store/parents.db

Verification:
    sqlite3 data/parent_store/parents.db "SELECT COUNT(*) FROM parents; SELECT COUNT(*) FROM child_parent_map;"
"""

import argparse
import json
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_INPUT = str(_PROJECT_ROOT / "scraped_data" / "sfs")
_DEFAULT_OUTPUT = str(_PROJECT_ROOT / "data" / "parent_store" / "parents.db")


def build_parent_store(
    input_dir: str = _DEFAULT_INPUT,
    output_path: str = _DEFAULT_OUTPUT,
) -> dict:
    """
    Build the SQLite parent store from scraped SFS JSON files.

    Args:
        input_dir: Directory containing sfs_*.json files
        output_path: Path for the output SQLite database

    Returns:
        Dict with statistics: parent_count, child_count, laws_processed
    """
    input_path = Path(input_dir)
    output_file = Path(output_path)

    # Create output directory
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Find all SFS JSON files (exclude fulltext files)
    json_files = sorted(input_path.glob("sfs_*.json"))
    json_files = [f for f in json_files if "_fulltext" not in f.name]

    if not json_files:
        logger.error(f"No SFS JSON files found in {input_path}")
        return {"parent_count": 0, "child_count": 0, "laws_processed": 0}

    logger.info(f"Found {len(json_files)} SFS JSON files in {input_path}")

    # Connect to SQLite with WAL mode for concurrent reads
    conn = sqlite3.connect(str(output_file))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create tables
    conn.executescript("""
        DROP TABLE IF EXISTS child_parent_map;
        DROP TABLE IF EXISTS parents;

        CREATE TABLE parents (
            parent_id TEXT PRIMARY KEY,
            sfs_nummer TEXT NOT NULL,
            law_name TEXT,
            kortnamn TEXT,
            kapitel TEXT,
            kapitel_rubrik TEXT,
            full_text TEXT NOT NULL,
            child_count INTEGER DEFAULT 0,
            references_json TEXT
        );

        CREATE TABLE child_parent_map (
            child_chunk_id TEXT PRIMARY KEY,
            parent_id TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES parents(parent_id)
        );

        CREATE INDEX idx_parents_sfs ON parents(sfs_nummer);
        CREATE INDEX idx_child_parent ON child_parent_map(parent_id);
    """)

    stats = {"parent_count": 0, "child_count": 0, "laws_processed": 0}

    for json_file in json_files:
        try:
            with open(json_file, encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Skipping {json_file.name}: {e}")
            continue

        sfs_nummer = doc.get("sfs_nummer", "")
        law_name = doc.get("titel", "")
        kortnamn = doc.get("kortnamn", "")
        chunks = doc.get("chunks", [])

        if not chunks:
            logger.debug(f"No chunks in {json_file.name}, skipping")
            continue

        # Group chunks by kapitel
        kapitel_groups: dict[str | None, list[dict]] = defaultdict(list)
        for chunk in chunks:
            kap = chunk.get("kapitel")
            kapitel_groups[kap].append(chunk)

        for kapitel, kap_chunks in kapitel_groups.items():
            # Build parent ID
            if kapitel:
                # Normalize: "2 kap." -> "2_kap"
                kap_normalized = kapitel.replace(" ", "_").replace(".", "")
                parent_id = f"{sfs_nummer}_{kap_normalized}"
            else:
                # Laws without kapitel — one parent per law
                parent_id = f"{sfs_nummer}_root"

            # Get kapitel rubrik from first chunk
            kapitel_rubrik = ""
            for c in kap_chunks:
                if c.get("kapitel_rubrik"):
                    kapitel_rubrik = c["kapitel_rubrik"]
                    break

            # Concatenate all § texts in order
            full_text_parts = []
            for c in kap_chunks:
                text = c.get("text", "")
                if text:
                    full_text_parts.append(text.strip())

            full_text = "\n\n".join(full_text_parts)

            # Aggregate cross-references from all children
            all_refs = []
            for c in kap_chunks:
                cross_refs = c.get("cross_refs")
                if cross_refs:
                    all_refs.extend(cross_refs)

            # Deduplicate refs by (ref_type, raw_match/raw_text)
            seen_refs = set()
            unique_refs = []
            for ref in all_refs:
                key = (
                    ref.get("ref_type", ""),
                    ref.get("raw_match", ref.get("raw_text", "")),
                )
                if key not in seen_refs:
                    seen_refs.add(key)
                    unique_refs.append(ref)

            refs_json = json.dumps(unique_refs, ensure_ascii=False) if unique_refs else None

            # Insert parent
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO parents
                    (parent_id, sfs_nummer, law_name, kortnamn, kapitel, kapitel_rubrik,
                     full_text, child_count, references_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        parent_id,
                        sfs_nummer,
                        law_name,
                        kortnamn,
                        kapitel,
                        kapitel_rubrik,
                        full_text,
                        len(kap_chunks),
                        refs_json,
                    ),
                )
                stats["parent_count"] += 1
            except sqlite3.IntegrityError as e:
                logger.warning(f"Duplicate parent {parent_id}: {e}")

            # Insert child→parent mappings
            for c in kap_chunks:
                chunk_id = c.get("chunk_id", "")
                if not chunk_id:
                    continue
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO child_parent_map (child_chunk_id, parent_id) VALUES (?, ?)",
                        (chunk_id, parent_id),
                    )
                    stats["child_count"] += 1
                except sqlite3.IntegrityError as e:
                    logger.warning(f"Duplicate child mapping {chunk_id}: {e}")

        stats["laws_processed"] += 1
        logger.debug(f"Processed {sfs_nummer}: {len(kapitel_groups)} kapitel")

    conn.commit()

    # Log final statistics
    cursor = conn.execute("SELECT COUNT(*) FROM parents")
    db_parents = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COUNT(*) FROM child_parent_map")
    db_children = cursor.fetchone()[0]

    conn.close()

    logger.info(
        f"Parent store built: {db_parents} parents, {db_children} children "
        f"from {stats['laws_processed']} laws → {output_file}"
    )

    return stats


def main():
    parser = argparse.ArgumentParser(description="Build SFS parent-child SQLite store")
    parser.add_argument(
        "--input",
        type=str,
        default=_DEFAULT_INPUT,
        help="Input directory with SFS JSON files",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=_DEFAULT_OUTPUT,
        help="Output SQLite database path",
    )
    args = parser.parse_args()

    stats = build_parent_store(input_dir=args.input, output_path=args.output)
    print(f"\nDone: {stats['parent_count']} parents, {stats['child_count']} children")


if __name__ == "__main__":
    main()
