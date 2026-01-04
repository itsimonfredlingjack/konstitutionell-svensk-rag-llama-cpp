#!/usr/bin/env python3
"""
Large DiVA File Parser - Handles 6 different JSON formats from Swedish universities.

Formats supported:
- GU (Göteborg): MODS - names[], abstract
- KI (Karolinska): PubMed - authors[{last_name, fore_name}], abstract
- KTH: swepub_mods - authors[], abstract
- LiU (Linköping): swepub_mods - authors[], abstract, genre
- Chalmers: oai_dc - creators[], titles[], descriptions[]
- LNU (Linnéuniversitetet): swepub_mods - authors[], abstract

Usage:
    python parse_large_diva.py                    # Parse all 6 files
    python parse_large_diva.py --file gu         # Parse single file
    python parse_large_diva.py --integrate       # Direct insert to corpus_bridge.db
    python parse_large_diva.py --count           # Just count records
"""

import argparse
import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import ijson

# Configuration
DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
OUTPUT_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/normalized")
BRIDGE_DB = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_bridge.db")

# File configurations
LARGE_FILES = {
    "gu": {
        "path": DATA_DIR / "diva_full_gu.json",
        "format": "mods",
        "institution": "Göteborgs universitet",
        "expected_count": 240774,
    },
    "ki": {
        "path": DATA_DIR / "diva_full_ki.json",
        "format": "pubmed",
        "institution": "Karolinska Institutet",
        "expected_count": 88670,
    },
    "kth": {
        "path": DATA_DIR / "diva_full_kth.json",
        "format": "swepub",
        "institution": "KTH Royal Institute of Technology",
        "expected_count": 57724,
    },
    "liu": {
        "path": DATA_DIR / "diva_full_liu.json",
        "format": "swepub_nested",
        "institution": "Linköpings universitet",
        "expected_count": 58221,
    },
    "chalmers": {
        "path": DATA_DIR / "diva_full_chalmers.json",
        "format": "oai_dc",
        "institution": "Chalmers tekniska högskola",
        "expected_count": 56000,
    },
    "lnu": {
        "path": DATA_DIR / "diva_full_lnu.json",
        "format": "swepub_lnu",
        "institution": "Linnéuniversitetet",
        "expected_count": 42502,
    },
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class NormalizedRecord:
    """Normalized document record."""

    doc_id: str
    source: str
    institution: str
    title: str
    authors: list
    abstract: Optional[str]
    year: Optional[str]
    genre: Optional[str]
    subjects: list
    raw_identifier: str


def normalize_authors_mods(names: list) -> list:
    """Normalize author names from MODS format (GU)."""
    authors = []
    for name in names:
        if isinstance(name, dict):
            n = name.get("name", "")
            role = name.get("role", "")
            if role == "aut":
                authors.append(n)
        elif isinstance(name, str):
            # Skip institutional entries
            if not any(x in name.lower() for x in ["universitet", "skolan", "institution"]):
                authors.append(name)
    return authors[:20]  # Limit to 20 authors


def normalize_authors_pubmed(authors: list) -> list:
    """Normalize author names from PubMed format (KI)."""
    result = []
    for a in authors:
        if isinstance(a, dict):
            last = a.get("last_name", "")
            first = a.get("fore_name", "") or a.get("initials", "")
            if last:
                result.append(f"{first} {last}".strip())
        elif isinstance(a, str):
            result.append(a)
    return result[:20]


def normalize_authors_swepub(authors: list) -> list:
    """Normalize author names from swepub format (KTH, LiU, LNU)."""
    result = []
    for a in authors:
        if isinstance(a, str):
            # Skip institutional entries
            if not any(
                x in a.lower() for x in ["universitet", "skolan", "institution", "fakultet"]
            ):
                # Remove birth year if present
                name = a.split(" 19")[0] if " 19" in a else a
                result.append(name.strip())
    return result[:20]


def normalize_authors_oai_dc(creators: list) -> list:
    """Normalize author names from OAI-DC format (Chalmers)."""
    return [c for c in creators if isinstance(c, str)][:20]


def extract_year(record: dict, format_type: str) -> Optional[str]:
    """Extract publication year from record."""
    if format_type == "pubmed":
        return record.get("pub_year")
    elif format_type in ("swepub", "swepub_nested", "swepub_lnu"):
        return record.get("year")
    elif format_type == "mods":
        # GU format doesn't have explicit year in sample
        datestamp = record.get("datestamp", "")
        if datestamp:
            return datestamp[:4]
    elif format_type == "oai_dc":
        # Try to extract from dates if present
        dates = record.get("dates", [])
        for d in dates:
            if isinstance(d, str) and len(d) >= 4:
                return d[:4]
    return None


def normalize_record(
    record: dict, source_code: str, format_type: str, institution: str
) -> Optional[NormalizedRecord]:
    """Normalize a record to standard format."""

    # Extract identifier
    if format_type == "pubmed":
        raw_id = record.get("pmid", "")
        doc_id = f"pubmed_{raw_id}"
    elif format_type == "mods":
        raw_id = record.get("identifier", "")
        doc_id = f"gu_{raw_id.split(':')[-1] if ':' in raw_id else raw_id}"
    elif format_type == "swepub":
        raw_id = record.get("id", "")
        doc_id = f"kth_{raw_id.split(':')[-1] if ':' in raw_id else raw_id}"
    elif format_type == "swepub_nested":
        raw_id = record.get("oai_identifier", "")
        doc_id = f"liu_{raw_id.split(':')[-1] if ':' in raw_id else raw_id}"
    elif format_type == "oai_dc":
        raw_id = record.get("identifier", "")
        doc_id = f"chalmers_{raw_id.split(':')[-1] if ':' in raw_id else raw_id}"
    elif format_type == "swepub_lnu":
        raw_id = record.get("oai_id", "")
        doc_id = f"lnu_{raw_id.split(':')[-1] if ':' in raw_id else raw_id}"
    else:
        return None

    if not doc_id or doc_id.endswith("_"):
        return None

    # Extract title
    if format_type == "oai_dc":
        titles = record.get("titles", [])
        title = titles[0] if titles else ""
    else:
        title = record.get("title", "")

    if not title:
        return None

    # Extract authors
    if format_type == "mods":
        authors = normalize_authors_mods(record.get("names", []))
    elif format_type == "pubmed":
        authors = normalize_authors_pubmed(record.get("authors", []))
    elif format_type in ("swepub", "swepub_nested", "swepub_lnu"):
        authors = normalize_authors_swepub(record.get("authors", []))
    elif format_type == "oai_dc":
        authors = normalize_authors_oai_dc(record.get("creators", []))
    else:
        authors = []

    # Extract abstract
    if format_type == "oai_dc":
        descriptions = record.get("descriptions", [])
        abstract = descriptions[0] if descriptions else None
    else:
        abstract = record.get("abstract")

    # Clean HTML from abstract
    if abstract:
        import re

        abstract = re.sub(r"<[^>]+>", "", abstract)
        abstract = abstract[:5000]  # Limit size

    # Extract year
    year = extract_year(record, format_type)

    # Extract genre/type
    genre = record.get("genre") or record.get("type")

    # Extract subjects
    subjects = record.get("subjects", [])
    if isinstance(subjects, list):
        subjects = [s for s in subjects if isinstance(s, str)][:20]
    else:
        subjects = []

    return NormalizedRecord(
        doc_id=doc_id,
        source=f"diva_{source_code}",
        institution=institution,
        title=title[:1000],
        authors=authors,
        abstract=abstract,
        year=year,
        genre=genre,
        subjects=subjects,
        raw_identifier=raw_id,
    )


def stream_records(filepath: Path) -> Iterator[dict]:
    """Stream parse records from large JSON file."""
    logger.info(f"Streaming {filepath.name}...")

    with open(filepath, "rb") as f:
        parser = ijson.items(f, "records.item")
        for record in parser:
            yield record


def count_records(filepath: Path) -> int:
    """Count records in file using streaming."""
    count = 0
    for _ in stream_records(filepath):
        count += 1
        if count % 10000 == 0:
            logger.info(f"  Counted {count:,} records...")
    return count


def parse_file(
    source_code: str, config: dict, output_path: Optional[Path] = None
) -> tuple[int, int]:
    """Parse a single file and optionally write normalized output."""
    filepath = config["path"]
    format_type = config["format"]
    institution = config["institution"]

    if not filepath.exists():
        logger.error(f"File not found: {filepath}")
        return 0, 0

    logger.info(f"Parsing {source_code.upper()} ({institution})...")
    logger.info(f"  Format: {format_type}, Expected: {config['expected_count']:,}")

    total = 0
    normalized = 0
    records_batch = []

    for record in stream_records(filepath):
        total += 1

        norm = normalize_record(record, source_code, format_type, institution)
        if norm:
            normalized += 1
            if output_path:
                records_batch.append(asdict(norm))

        if total % 25000 == 0:
            logger.info(f"  Processed {total:,} / normalized {normalized:,}")

            # Write batch to file
            if output_path and records_batch:
                mode = "a" if total > 25000 else "w"
                with open(output_path, mode) as f:
                    for r in records_batch:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                records_batch = []

    # Write remaining records
    if output_path and records_batch:
        mode = "a" if total > 25000 else "w"
        with open(output_path, mode) as f:
            for r in records_batch:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info(
        f"  Complete: {total:,} total, {normalized:,} normalized ({normalized*100/total:.1f}%)"
    )
    return total, normalized


def compute_checksum(data: dict) -> str:
    """Compute stable checksum."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def integrate_to_bridge(source_code: str, config: dict) -> int:
    """Parse and directly insert into corpus_bridge.db."""
    filepath = config["path"]
    format_type = config["format"]
    institution = config["institution"]

    if not filepath.exists():
        logger.error(f"File not found: {filepath}")
        return 0

    if not BRIDGE_DB.exists():
        logger.error(f"Bridge DB not found: {BRIDGE_DB}")
        return 0

    conn = sqlite3.connect(BRIDGE_DB)
    conn.execute("PRAGMA journal_mode=WAL")

    logger.info(f"Integrating {source_code.upper()} into corpus_bridge.db...")

    total = 0
    inserted = 0

    for record in stream_records(filepath):
        total += 1

        norm = normalize_record(record, source_code, format_type, institution)
        if not norm:
            continue

        checksum_data = {"id": norm.doc_id, "title": norm.title[:100], "source": norm.source}
        checksum = compute_checksum(checksum_data)

        metadata = {
            "authors": norm.authors,
            "year": norm.year,
            "genre": norm.genre,
            "subjects": norm.subjects[:10],
            "institution": norm.institution,
        }

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO document_inventory
                (doc_id, source, source_file, document_type, title, metadata_json, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    norm.doc_id,
                    norm.source,
                    str(filepath),
                    "academic",
                    norm.title[:500],
                    json.dumps(metadata, ensure_ascii=False)[:5000],
                    checksum,
                ),
            )
            inserted += 1
        except Exception as e:
            if "UNIQUE constraint" not in str(e):
                logger.warning(f"Insert error: {e}")

        if total % 10000 == 0:
            conn.commit()
            logger.info(f"  Processed {total:,} / inserted {inserted:,}")

    conn.commit()

    # Update progress tracking
    conn.execute(
        """
        INSERT OR REPLACE INTO import_progress
        (source, source_file, total_records, processed_records, status, started_at)
        VALUES (?, ?, ?, ?, 'inventoried', datetime('now'))
    """,
        (f"diva_{source_code}_large", str(filepath), total, inserted),
    )
    conn.commit()
    conn.close()

    logger.info(f"  Complete: {total:,} total, {inserted:,} inserted")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Parse large DiVA files")
    parser.add_argument("--file", "-f", choices=list(LARGE_FILES.keys()), help="Parse single file")
    parser.add_argument(
        "--integrate", "-i", action="store_true", help="Direct insert to corpus_bridge.db"
    )
    parser.add_argument("--count", "-c", action="store_true", help="Just count records")
    parser.add_argument("--output", "-o", action="store_true", help="Output normalized JSONL files")
    args = parser.parse_args()

    # Ensure output directory exists
    if args.output:
        OUTPUT_DIR.mkdir(exist_ok=True)

    files_to_process = [args.file] if args.file else list(LARGE_FILES.keys())

    grand_total = 0
    grand_normalized = 0

    for source_code in files_to_process:
        config = LARGE_FILES[source_code]

        if args.count:
            count = count_records(config["path"])
            logger.info(f"{source_code.upper()}: {count:,} records")
            grand_total += count
        elif args.integrate:
            inserted = integrate_to_bridge(source_code, config)
            grand_normalized += inserted
        else:
            output_path = OUTPUT_DIR / f"{source_code}_normalized.jsonl" if args.output else None
            total, normalized = parse_file(source_code, config, output_path)
            grand_total += total
            grand_normalized += normalized

    if args.count:
        logger.info(f"\nGrand total: {grand_total:,} records")
    elif args.integrate:
        logger.info(f"\nGrand total inserted: {grand_normalized:,} records")
    else:
        logger.info(f"\nGrand total: {grand_total:,} / {grand_normalized:,} normalized")


if __name__ == "__main__":
    main()
