#!/usr/bin/env python3
"""
Corpus Bridge - Connects 1.7M existing documents to materialized views system.

Features:
- Inventories existing document sources (DIVA, scrapes, ChromaDB)
- Generates import queue events (SQLite, PostgreSQL-ready schema)
- Triggers n8n materialize_worker with rate limiting
- Resume-capable with checkpoint tracking

Usage:
    python corpus_bridge.py inventory          # Step 1: Inventory all sources
    python corpus_bridge.py generate-queue     # Step 2: Generate import queue
    python corpus_bridge.py trigger [--rate 100]  # Step 3: Trigger n8n webhook
    python corpus_bridge.py status             # Show current progress
"""

import argparse
import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests

# Configuration
CONFIG = {
    "data_dir": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data"),
    "root_dir": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI"),
    "chromadb_path": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data"),
    "bridge_db": Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/corpus_bridge.db"),
    "n8n_webhook": "http://localhost:5678/webhook/second-brain/ingest",
    "batch_size": 10_000,
    "default_rate_limit": 100,  # events/sec
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(CONFIG["root_dir"] / "corpus_bridge.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


@dataclass
class DocumentRecord:
    """Normalized document record for the inbox queue."""

    doc_id: str
    source: str
    source_file: str
    document_type: str
    title: str | None
    metadata_json: str
    checksum: str
    status: str = "pending"
    created_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


def init_database(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with PostgreSQL-compatible schema."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Schema designed to be portable to PostgreSQL
    conn.executescript("""
        -- Document inventory from all sources
        CREATE TABLE IF NOT EXISTS document_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            document_type TEXT NOT NULL,
            title TEXT,
            metadata_json TEXT,
            checksum TEXT NOT NULL,
            discovered_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source, doc_id)
        );

        -- Import event queue (inbox_events equivalent)
        CREATE TABLE IF NOT EXISTS inbox_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            doc_id TEXT NOT NULL,
            event_type TEXT DEFAULT 'import',
            payload_json TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            processed_at TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            FOREIGN KEY (doc_id) REFERENCES document_inventory(doc_id)
        );

        -- Progress tracking for resume capability
        CREATE TABLE IF NOT EXISTS import_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_file TEXT NOT NULL,
            total_records INTEGER,
            processed_records INTEGER DEFAULT 0,
            queued_records INTEGER DEFAULT 0,
            triggered_records INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            last_checkpoint TEXT,
            UNIQUE(source, source_file)
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox_events(status);
        CREATE INDEX IF NOT EXISTS idx_inbox_priority ON inbox_events(priority DESC);
        CREATE INDEX IF NOT EXISTS idx_inventory_source ON document_inventory(source);
        CREATE INDEX IF NOT EXISTS idx_progress_status ON import_progress(status);
    """)
    conn.commit()
    return conn


def compute_checksum(data: dict) -> str:
    """Compute stable checksum for deduplication."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def stream_count_records(filepath: Path) -> int:
    """Stream parse large JSON files to count records."""
    try:
        import ijson
    except ImportError:
        # Fallback: count by looking for record patterns
        count = 0
        with open(filepath) as f:
            for line in f:
                if '"identifier":' in line or '"id":' in line:
                    count += 1
        return count

    count = 0
    try:
        with open(filepath, "rb") as f:
            parser = ijson.items(f, "records.item")
            for _ in parser:
                count += 1
    except Exception:
        pass
    return count


def stream_parse_records(filepath: Path) -> Iterator[dict]:
    """Stream parse large JSON files and yield records."""
    try:
        import ijson

        with open(filepath, "rb") as f:
            parser = ijson.items(f, "records.item")
            for record in parser:
                yield record
    except ImportError:
        # Fallback: try to parse normally
        try:
            with open(filepath) as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                for record in data["records"]:
                    yield record
            elif isinstance(data, list):
                for record in data:
                    yield record
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Stream parse failed for {filepath}: {e}")


def scan_diva_files(data_dir: Path) -> Iterator[tuple[Path, int]]:
    """Scan DIVA JSON files and yield (path, record_count)."""
    for f in sorted(data_dir.glob("diva_*.json")):
        if "checkpoint" in f.name or "summary" in f.name:
            continue
        try:
            with open(f) as file:
                data = json.load(file)
            if isinstance(data, list):
                yield f, len(data)
            elif isinstance(data, dict):
                # Handle files with 'records' array inside object
                records = data.get("records", [])
                if records:
                    yield f, len(records)
                elif data.get("total_records"):
                    yield f, data["total_records"]
        except json.JSONDecodeError as e:
            # Try streaming parse for large files
            logger.info(f"Attempting streaming parse for {f.name}...")
            count = stream_count_records(f)
            if count > 0:
                yield f, count
            else:
                logger.warning(f"Error reading {f}: {e}")
        except Exception as e:
            logger.warning(f"Error reading {f}: {e}")


def scan_scrape_files(root_dir: Path) -> Iterator[tuple[Path, int]]:
    """Scan scrape result files."""
    for pattern in ["*_scrape*.json", "*_report.json", "*_index*.json"]:
        for f in root_dir.glob(pattern):
            try:
                with open(f) as file:
                    data = json.load(file)
                if isinstance(data, list):
                    count = len(data)
                elif isinstance(data, dict):
                    count = (
                        len(data.get("documents", []))
                        or len(data.get("results", []))
                        or len(data.get("records", []))
                        or data.get("total_documents", 0)
                        or 1
                    )
                else:
                    count = 0
                if count > 0:
                    yield f, count
            except Exception as e:
                logger.warning(f"Error reading {f}: {e}")


def inventory_source(conn: sqlite3.Connection, source_path: Path, source_type: str):
    """Process a single source file and add to inventory."""
    logger.info(f"Inventorying {source_path.name}...")

    # Determine document type from source
    if "diva" in source_path.name.lower():
        doc_type = "academic"
    elif any(x in source_path.name.lower() for x in ["scrape", "report"]):
        doc_type = "myndighet"
    else:
        doc_type = "unknown"

    # Extract source identifier
    source_id = source_path.stem.replace("_full", "").replace("_scrape", "")

    # Check file size - use streaming for large files
    file_size = source_path.stat().st_size
    use_streaming = file_size > 50_000_000  # 50MB threshold

    if use_streaming:
        logger.info(f"  Large file ({file_size / 1_000_000:.1f}MB), using streaming parser...")
        records = stream_parse_records(source_path)
    else:
        try:
            with open(source_path) as f:
                data = json.load(f)
            if isinstance(data, list):
                records = iter(data)
            elif isinstance(data, dict):
                rec_list = (
                    data.get("documents") or data.get("results") or data.get("records") or [data]
                )
                records = iter(rec_list)
            else:
                records = iter([])
        except json.JSONDecodeError:
            logger.info("  JSON decode error, trying streaming parser...")
            records = stream_parse_records(source_path)
        except Exception as e:
            logger.error(f"Failed to load {source_path}: {e}")
            return 0

    inserted = 0
    total_seen = 0
    for i, record in enumerate(records):
        total_seen += 1
        if not isinstance(record, dict):
            continue

        # Generate document ID
        doc_id = (
            record.get("identifier") or record.get("id") or record.get("url") or f"{source_id}_{i}"
        )

        title = record.get("title") or record.get("name") or record.get("document_title") or None

        # Only compute checksum on limited data to avoid memory issues
        checksum_data = {"id": doc_id, "title": title, "source": source_id}
        checksum = compute_checksum(checksum_data)

        # Limit metadata to save space
        metadata_limited = {
            k: v
            for k, v in record.items()
            if k
            in (
                "identifier",
                "id",
                "title",
                "authors",
                "date",
                "url",
                "genre",
                "language",
                "publisher",
                "subjects",
                "type",
            )
        }

        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO document_inventory
                (doc_id, source, source_file, document_type, title, metadata_json, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    str(doc_id),
                    source_id,
                    str(source_path),
                    doc_type,
                    title[:500] if title else None,
                    json.dumps(metadata_limited, ensure_ascii=False)[:5000],
                    checksum,
                ),
            )
            inserted += 1
        except Exception as e:
            if "UNIQUE constraint" not in str(e):
                logger.warning(f"Insert error for {doc_id}: {e}")

        if inserted % 10000 == 0 and inserted > 0:
            conn.commit()
            logger.info(f"  ...inserted {inserted:,} records")

    conn.commit()

    # Update progress tracking
    conn.execute(
        """
        INSERT OR REPLACE INTO import_progress
        (source, source_file, total_records, processed_records, status, started_at)
        VALUES (?, ?, ?, ?, 'inventoried', datetime('now'))
    """,
        (source_id, str(source_path), total_seen, inserted),
    )
    conn.commit()

    logger.info(f"  Completed: {inserted:,} / {total_seen:,} records")
    return inserted


def inventory_chromadb(conn: sqlite3.Connection) -> int:
    """Inventory documents from ChromaDB collections."""
    try:
        import chromadb
    except ImportError:
        logger.warning("chromadb not installed, skipping ChromaDB inventory")
        return 0

    chromadb_path = CONFIG["chromadb_path"]
    if not chromadb_path.exists():
        logger.warning(f"ChromaDB path not found: {chromadb_path}")
        return 0

    client = chromadb.PersistentClient(path=str(chromadb_path))
    collections = client.list_collections()

    total_inserted = 0
    for coll_info in collections:
        coll_name = coll_info.name
        coll = client.get_collection(coll_name)
        count = coll.count()

        if count == 0:
            continue

        logger.info(f"  Processing collection '{coll_name}' ({count:,} docs)...")

        # Process in batches to avoid memory issues
        batch_size = 5000
        offset = 0
        inserted = 0

        while offset < count:
            results = coll.get(limit=batch_size, offset=offset, include=["metadatas"])

            for i, doc_id in enumerate(results["ids"]):
                metadata = results["metadatas"][i] if results["metadatas"] else {}

                # Generate stable checksum
                checksum_data = {
                    "id": doc_id,
                    "collection": coll_name,
                    "title": metadata.get("title", "")[:100],
                }
                checksum = compute_checksum(checksum_data)

                # Determine document type from collection name
                if "riksdag" in coll_name.lower():
                    doc_type = "riksdag"
                elif "gov" in coll_name.lower():
                    doc_type = "government"
                else:
                    doc_type = "chromadb"

                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO document_inventory
                        (doc_id, source, source_file, document_type, title, metadata_json, checksum)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            f"chromadb_{coll_name}_{doc_id}",
                            f"chromadb_{coll_name}",
                            str(chromadb_path),
                            doc_type,
                            metadata.get("title", "")[:500] if metadata.get("title") else None,
                            json.dumps(metadata, ensure_ascii=False)[:5000],
                            checksum,
                        ),
                    )
                    inserted += 1
                except Exception as e:
                    if "UNIQUE constraint" not in str(e):
                        logger.warning(f"ChromaDB insert error: {e}")

            offset += batch_size
            if inserted % 50000 == 0 and inserted > 0:
                conn.commit()
                logger.info(f"    ...inserted {inserted:,} records")

        conn.commit()
        total_inserted += inserted
        logger.info(f"    Completed: {inserted:,} records from {coll_name}")

        # Update progress tracking
        conn.execute(
            """
            INSERT OR REPLACE INTO import_progress
            (source, source_file, total_records, processed_records, status, started_at)
            VALUES (?, ?, ?, ?, 'inventoried', datetime('now'))
        """,
            (f"chromadb_{coll_name}", str(chromadb_path), count, inserted),
        )
        conn.commit()

    return total_inserted


def cmd_inventory(args):
    """Step 1: Inventory all existing documents."""
    logger.info("=" * 60)
    logger.info("CORPUS BRIDGE - INVENTORY PHASE")
    logger.info("=" * 60)

    conn = init_database(CONFIG["bridge_db"])

    total_files = 0
    total_records = 0

    # ChromaDB collections (Riksdagen + government docs)
    logger.info("\n--- ChromaDB Collections ---")
    chromadb_count = inventory_chromadb(conn)
    total_records += chromadb_count
    logger.info(f"  ChromaDB total: {chromadb_count:,} records")

    # DIVA files (academic publications)
    logger.info("\n--- DIVA Academic Publications ---")
    for path, _count in scan_diva_files(CONFIG["data_dir"]):
        inserted = inventory_source(conn, path, "diva")
        total_files += 1

    # Scrape files (government documents)
    logger.info("\n--- Government Agency Scrapes ---")
    for path, _count in scan_scrape_files(CONFIG["root_dir"]):
        inserted = inventory_source(conn, path, "scrape")
        total_files += 1

    # Data directory JSON files
    logger.info("\n--- Data Directory Files ---")
    for path, _count in scan_scrape_files(CONFIG["data_dir"]):
        if "diva" not in path.name.lower():
            inserted = inventory_source(conn, path, "data")
            total_files += 1
            total_records += inserted

    # Summary
    cursor = conn.execute("SELECT COUNT(*) FROM document_inventory")
    total_inventory = cursor.fetchone()[0]

    cursor = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM document_inventory GROUP BY source ORDER BY cnt DESC LIMIT 20"
    )
    by_source = cursor.fetchall()

    logger.info("\n" + "=" * 60)
    logger.info("INVENTORY COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Files processed: {total_files:,}")
    logger.info(f"Total records in inventory: {total_inventory:,}")
    logger.info("\nTop sources:")
    for source, cnt in by_source:
        logger.info(f"  {source}: {cnt:,}")

    conn.close()
    return total_inventory


def cmd_generate_queue(args):
    """Step 2: Generate import queue from inventory."""
    logger.info("=" * 60)
    logger.info("CORPUS BRIDGE - GENERATE QUEUE PHASE")
    logger.info("=" * 60)

    conn = init_database(CONFIG["bridge_db"])
    batch_size = args.batch_size or CONFIG["batch_size"]

    # Get unqueued documents
    cursor = conn.execute("""
        SELECT di.id, di.doc_id, di.source, di.document_type, di.title, di.metadata_json
        FROM document_inventory di
        LEFT JOIN inbox_events ie ON di.doc_id = ie.doc_id
        WHERE ie.id IS NULL
        ORDER BY di.id
    """)

    queued = 0
    batch = []

    for row in cursor:
        _inv_id, doc_id, source, doc_type, title, metadata = row

        event_id = f"import_{doc_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Parse metadata, handle truncated JSON gracefully
        try:
            metadata_dict = json.loads(metadata) if metadata else {}
        except json.JSONDecodeError:
            metadata_dict = {"raw": metadata[:500] if metadata else ""}

        payload = {
            "action": "import",
            "doc_id": doc_id,
            "source": source,
            "document_type": doc_type,
            "title": title,
            "metadata": metadata_dict,
        }

        batch.append(
            (
                event_id,
                doc_id,
                "import",
                json.dumps(payload, ensure_ascii=False),
                "pending",
                1 if doc_type == "myndighet" else 0,  # Priority boost for government docs
            )
        )

        if len(batch) >= batch_size:
            conn.executemany(
                """
                INSERT OR IGNORE INTO inbox_events
                (event_id, doc_id, event_type, payload_json, status, priority)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                batch,
            )
            conn.commit()
            queued += len(batch)
            logger.info(f"Queued {queued:,} events...")
            batch = []

    # Final batch
    if batch:
        conn.executemany(
            """
            INSERT OR IGNORE INTO inbox_events
            (event_id, doc_id, event_type, payload_json, status, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            batch,
        )
        conn.commit()
        queued += len(batch)

    # Summary
    cursor = conn.execute("SELECT status, COUNT(*) FROM inbox_events GROUP BY status")
    status_counts = dict(cursor.fetchall())

    logger.info("\n" + "=" * 60)
    logger.info("QUEUE GENERATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"New events queued: {queued:,}")
    logger.info("Queue status:")
    for status, count in status_counts.items():
        logger.info(f"  {status}: {count:,}")

    conn.close()
    return queued


def send_webhook_batch(webhook_url: str, events: list) -> tuple[int, int]:
    """Send batch of events to n8n webhook. Returns (success, failed)."""
    success = 0
    failed = 0

    for event in events:
        try:
            payload = json.loads(event[3])  # payload_json
            response = requests.post(
                webhook_url, json=payload, timeout=5, headers={"Content-Type": "application/json"}
            )
            if response.status_code in (200, 201, 202):
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return success, failed


def cmd_trigger(args):
    """Step 3: Trigger n8n webhook for queued events."""
    logger.info("=" * 60)
    logger.info("CORPUS BRIDGE - TRIGGER PHASE")
    logger.info("=" * 60)

    conn = init_database(CONFIG["bridge_db"])
    rate_limit = args.rate or CONFIG["default_rate_limit"]
    webhook_url = args.webhook or CONFIG["n8n_webhook"]
    dry_run = args.dry_run
    doc_filter = getattr(args, "filter", None)

    logger.info(f"Rate limit: {rate_limit} events/sec")
    logger.info(f"Webhook: {webhook_url}")
    logger.info(f"Dry run: {dry_run}")
    if doc_filter:
        logger.info(f"Filter: document_type = '{doc_filter}'")

    # Get pending events with optional filter
    if doc_filter:
        cursor = conn.execute(
            """
            SELECT ie.id, ie.event_id, ie.doc_id, ie.payload_json
            FROM inbox_events ie
            JOIN document_inventory di ON ie.doc_id = di.doc_id
            WHERE ie.status = 'pending' AND di.document_type = ?
            ORDER BY ie.priority DESC, ie.id
            LIMIT ?
        """,
            (doc_filter, args.limit or 1_000_000),
        )
    else:
        cursor = conn.execute(
            """
            SELECT id, event_id, doc_id, payload_json
            FROM inbox_events
            WHERE status = 'pending'
            ORDER BY priority DESC, id
            LIMIT ?
        """,
            (args.limit or 1_000_000,),
        )

    events = cursor.fetchall()
    logger.info(f"Events to process: {len(events):,}")

    if not events:
        logger.info("No pending events")
        return 0

    if dry_run:
        logger.info("[DRY RUN] Would trigger events, exiting")
        return len(events)

    # Process with rate limiting
    processed = 0
    success = 0
    failed = 0
    interval = 1.0 / rate_limit

    for event in events:
        # event_id = event[1]

        try:
            payload = json.loads(event[3])
            response = requests.post(
                webhook_url, json=payload, timeout=10, headers={"Content-Type": "application/json"}
            )

            if response.status_code in (200, 201, 202):
                conn.execute(
                    """
                    UPDATE inbox_events
                    SET status = 'triggered', processed_at = datetime('now')
                    WHERE id = ?
                """,
                    (event[0],),
                )
                success += 1
            else:
                conn.execute(
                    """
                    UPDATE inbox_events
                    SET status = 'failed',
                        error_message = ?,
                        retry_count = retry_count + 1
                    WHERE id = ?
                """,
                    (f"HTTP {response.status_code}", event[0]),
                )
                failed += 1

        except Exception as e:
            conn.execute(
                """
                UPDATE inbox_events
                SET status = 'failed',
                    error_message = ?,
                    retry_count = retry_count + 1
                WHERE id = ?
            """,
                (str(e)[:500], event[0]),
            )
            failed += 1

        processed += 1

        if processed % 100 == 0:
            conn.commit()
            logger.info(
                f"Processed {processed:,} / {len(events):,} (success: {success:,}, failed: {failed:,})"
            )

        time.sleep(interval)

    conn.commit()

    logger.info("\n" + "=" * 60)
    logger.info("TRIGGER PHASE COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Processed: {processed:,}")
    logger.info(f"Success: {success:,}")
    logger.info(f"Failed: {failed:,}")

    conn.close()
    return processed


def cmd_status(args):
    """Show current bridge status."""
    if not CONFIG["bridge_db"].exists():
        print("Bridge database not initialized. Run 'inventory' first.")
        return

    conn = sqlite3.connect(CONFIG["bridge_db"])

    print("\n" + "=" * 60)
    print("CORPUS BRIDGE STATUS")
    print("=" * 60)

    # Inventory stats
    cursor = conn.execute("SELECT COUNT(*) FROM document_inventory")
    total_inventory = cursor.fetchone()[0]
    print(f"\nDocument Inventory: {total_inventory:,}")

    cursor = conn.execute("""
        SELECT document_type, COUNT(*)
        FROM document_inventory
        GROUP BY document_type
    """)
    print("  By type:")
    for doc_type, count in cursor.fetchall():
        print(f"    {doc_type}: {count:,}")

    # Queue stats
    cursor = conn.execute("SELECT COUNT(*) FROM inbox_events")
    total_queue = cursor.fetchone()[0]
    print(f"\nEvent Queue: {total_queue:,}")

    cursor = conn.execute("""
        SELECT status, COUNT(*)
        FROM inbox_events
        GROUP BY status
    """)
    print("  By status:")
    for status, count in cursor.fetchall():
        print(f"    {status}: {count:,}")

    # Progress stats
    cursor = conn.execute("""
        SELECT status, COUNT(*), SUM(total_records), SUM(processed_records)
        FROM import_progress
        GROUP BY status
    """)
    print("\nSource Progress:")
    for status, file_count, total, processed in cursor.fetchall():
        print(f"  {status}: {file_count} files, {processed or 0:,} / {total or 0:,} records")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Corpus Bridge - Connect existing documents to materialized views",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # inventory
    # inv_parser = subparsers.add_parser("inventory", help="Inventory all document sources")

    # generate-queue
    queue_parser = subparsers.add_parser("generate-queue", help="Generate import queue")
    queue_parser.add_argument(
        "--batch-size", type=int, help=f"Batch size (default: {CONFIG['batch_size']})"
    )

    # trigger
    trigger_parser = subparsers.add_parser("trigger", help="Trigger n8n webhook")
    trigger_parser.add_argument(
        "--rate", type=int, help=f"Events per second (default: {CONFIG['default_rate_limit']})"
    )
    trigger_parser.add_argument("--webhook", type=str, help="Override webhook URL")
    trigger_parser.add_argument("--limit", type=int, help="Max events to process")
    trigger_parser.add_argument(
        "--filter", type=str, help="Filter by document_type (e.g., 'academic', 'government')"
    )
    trigger_parser.add_argument(
        "--dry-run", action="store_true", help="Don't actually send webhooks"
    )

    # status
    # status_parser = subparsers.add_parser("status", help="Show current status")

    args = parser.parse_args()

    if args.command == "inventory":
        cmd_inventory(args)
    elif args.command == "generate-queue":
        cmd_generate_queue(args)
    elif args.command == "trigger":
        cmd_trigger(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
