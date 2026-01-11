#!/usr/bin/env python3
"""
SQLite state tracking for kommun swarm orchestration.
Provides ACID-guaranteed task management for 290 municipalities.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path("kommun_tasks.db")


@dataclass
class KommunTask:
    id: str  # kommun_kod
    namn: str
    url: str
    status: str = "pending"  # pending|running|done|failed
    batch_id: int | None = None
    priority: int = 3
    started_at: str | None = None
    completed_at: str | None = None
    result: str | None = None  # JSON string
    error: str | None = None


@dataclass
class Dokument:
    """Representation of a harvested document."""

    id: int | None = None
    kommun_kod: str = ""
    kalla_url: str = ""  # källa_url
    titel: str | None = None
    dokument_datum: str | None = None
    filtyp: str | None = None
    storlek_bytes: int | None = None
    sha256: str | None = None
    relevans_tagg: str | None = None  # protokoll|beslut|policy|rapport|upphandling
    kraver_maskning: bool = False  # kräver_maskning
    kvalitet_score: int | None = None  # 1-5
    hamtat: str | None = None  # hämtat timestamp
    lokal_sokvag: str | None = None  # lokal_sökväg
    indexerad: bool = False


def init_db():
    """Initialize database with schema."""
    conn = sqlite3.connect(DB_PATH)

    # Kommuner table (existing)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kommuner (
            id TEXT PRIMARY KEY,
            namn TEXT NOT NULL,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            batch_id INTEGER,
            priority INTEGER DEFAULT 3,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON kommuner(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_batch ON kommuner(batch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON kommuner(priority DESC)")

    # Dokument table (new - for tracking harvested documents)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dokument (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kommun_kod TEXT NOT NULL,
            kalla_url TEXT NOT NULL UNIQUE,
            titel TEXT,
            dokument_datum TEXT,
            filtyp TEXT,
            storlek_bytes INTEGER,
            sha256 TEXT,
            relevans_tagg TEXT,
            kraver_maskning BOOLEAN DEFAULT 0,
            kvalitet_score INTEGER,
            hamtat TEXT NOT NULL,
            lokal_sokvag TEXT,
            indexerad BOOLEAN DEFAULT 0,
            FOREIGN KEY (kommun_kod) REFERENCES kommuner(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dok_kommun ON dokument(kommun_kod)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dok_sha ON dokument(sha256)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dok_tagg ON dokument(relevans_tagg)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dok_indexerad ON dokument(indexerad)")

    # Fel_logg table (new - for error logging)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fel_logg (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kommun_kod TEXT,
            url TEXT,
            fel_typ TEXT,
            meddelande TEXT,
            timestamp TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fel_kommun ON fel_logg(kommun_kod)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fel_typ ON fel_logg(fel_typ)")

    conn.commit()
    conn.close()


def load_manifest(manifest_path: str):
    """Load kommun manifest and populate database."""
    init_db()

    with open(manifest_path) as f:
        manifest = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    for task in manifest["tasks"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO kommuner (id, namn, url, priority, status)
            VALUES (?, ?, ?, ?, 'pending')
        """,
            (task["id"], task["namn"], task["url"], task.get("priority", 3)),
        )

    conn.commit()
    conn.close()
    print(f"Loaded {len(manifest['tasks'])} kommuner")


def claim_next_task(batch_id: int) -> KommunTask | None:
    """
    Atomically claim next pending task for a batch.
    Returns None if no pending tasks remain.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Atomic claim with UPDATE ... RETURNING
    cursor = conn.execute(
        """
        UPDATE kommuner
        SET status = 'running',
            batch_id = ?,
            started_at = ?
        WHERE id = (
            SELECT id FROM kommuner
            WHERE status = 'pending'
            ORDER BY priority DESC, id
            LIMIT 1
        )
        RETURNING *
    """,
        (batch_id, datetime.now().isoformat()),
    )

    row = cursor.fetchone()
    conn.commit()
    conn.close()

    if row:
        return KommunTask(**dict(row))
    return None


def complete_task(kommun_id: str, result: dict):
    """Mark task as completed with result."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE kommuner
        SET status = 'done',
            completed_at = ?,
            result = ?
        WHERE id = ?
    """,
        (datetime.now().isoformat(), json.dumps(result), kommun_id),
    )
    conn.commit()
    conn.close()


def fail_task(kommun_id: str, error: str):
    """Mark task as failed with error message."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        UPDATE kommuner
        SET status = 'failed',
            completed_at = ?,
            error = ?
        WHERE id = ?
    """,
        (datetime.now().isoformat(), error, kommun_id),
    )
    conn.commit()
    conn.close()


def get_batch_status(batch_id: int) -> dict:
    """Get status summary for a batch."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """
        SELECT status, COUNT(*) as count
        FROM kommuner
        WHERE batch_id = ?
        GROUP BY status
    """,
        (batch_id,),
    )

    status = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return status


def get_overall_progress() -> dict:
    """Get overall progress across all tasks."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM kommuner
    """)

    row = cursor.fetchone()
    conn.close()

    return {
        "total": row[0],
        "done": row[1],
        "failed": row[2],
        "running": row[3],
        "pending": row[4],
        "progress_pct": round(row[1] / row[0] * 100, 1) if row[0] > 0 else 0,
    }


def get_failed_tasks() -> list[KommunTask]:
    """Get all failed tasks for retry."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT * FROM kommuner WHERE status = 'failed'
    """)

    tasks = [KommunTask(**dict(row)) for row in cursor.fetchall()]
    conn.close()
    return tasks


def reset_failed_tasks():
    """Reset failed tasks to pending for retry."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        UPDATE kommuner
        SET status = 'pending',
            batch_id = NULL,
            started_at = NULL,
            completed_at = NULL,
            error = NULL
        WHERE status = 'failed'
    """)
    count = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"Reset {count} failed tasks to pending")


def export_results(output_path: str):
    """Export all completed results to JSON."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT * FROM kommuner WHERE status = 'done'
    """)

    results = []
    for row in cursor.fetchall():
        data = dict(row)
        if data["result"]:
            data["result"] = json.loads(data["result"])
        results.append(data)

    conn.close()

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Exported {len(results)} results to {output_path}")


def aggregate_stats() -> dict:
    """Aggregate CMS and diarium distribution from results."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT result FROM kommuner WHERE status = 'done' AND result IS NOT NULL
    """)

    cms_counts = {}
    diarium_counts = {}
    total_docs = 0

    for row in cursor.fetchall():
        result = json.loads(row[0])

        cms = result.get("cms", "unknown")
        cms_counts[cms] = cms_counts.get(cms, 0) + 1

        diarium = result.get("diarium", "unknown")
        diarium_counts[diarium] = diarium_counts.get(diarium, 0) + 1

        docs = result.get("doc_count_estimate") or 0
        total_docs += docs

    conn.close()

    return {
        "cms_distribution": cms_counts,
        "diarium_distribution": diarium_counts,
        "total_estimated_docs": total_docs,
    }


# ============================================================
# Document tracking functions (for harvest phase)
# ============================================================


def add_dokument(doc: Dokument) -> int:
    """Add a harvested document to the database. Returns document ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO dokument
        (kommun_kod, kalla_url, titel, dokument_datum, filtyp, storlek_bytes,
         sha256, relevans_tagg, kraver_maskning, kvalitet_score, hamtat, lokal_sokvag, indexerad)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            doc.kommun_kod,
            doc.kalla_url,
            doc.titel,
            doc.dokument_datum,
            doc.filtyp,
            doc.storlek_bytes,
            doc.sha256,
            doc.relevans_tagg,
            doc.kraver_maskning,
            doc.kvalitet_score,
            doc.hamtat,
            doc.lokal_sokvag,
            doc.indexerad,
        ),
    )
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def add_dokument_batch(docs: list[Dokument]) -> int:
    """Add multiple documents in a single transaction. Returns count added."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO dokument
        (kommun_kod, kalla_url, titel, dokument_datum, filtyp, storlek_bytes,
         sha256, relevans_tagg, kraver_maskning, kvalitet_score, hamtat, lokal_sokvag, indexerad)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            (
                d.kommun_kod,
                d.kalla_url,
                d.titel,
                d.dokument_datum,
                d.filtyp,
                d.storlek_bytes,
                d.sha256,
                d.relevans_tagg,
                d.kraver_maskning,
                d.kvalitet_score,
                d.hamtat,
                d.lokal_sokvag,
                d.indexerad,
            )
            for d in docs
        ],
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def get_dokument_by_kommun(kommun_kod: str) -> list[Dokument]:
    """Get all documents for a specific kommun."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT * FROM dokument WHERE kommun_kod = ?
    """,
        (kommun_kod,),
    )

    docs = [Dokument(**dict(row)) for row in cursor.fetchall()]
    conn.close()
    return docs


def get_unindexed_dokument(limit: int = 100) -> list[Dokument]:
    """Get documents that haven't been indexed to ChromaDB yet."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        """
        SELECT * FROM dokument WHERE indexerad = 0 LIMIT ?
    """,
        (limit,),
    )

    docs = [Dokument(**dict(row)) for row in cursor.fetchall()]
    conn.close()
    return docs


def mark_dokument_indexerad(doc_ids: list[int]):
    """Mark documents as indexed in ChromaDB."""
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        """
        UPDATE dokument SET indexerad = 1 WHERE id = ?
    """,
        [(id,) for id in doc_ids],
    )
    conn.commit()
    conn.close()


def dokument_exists(sha256: str) -> bool:
    """Check if a document with this hash already exists (deduplication)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """
        SELECT 1 FROM dokument WHERE sha256 = ? LIMIT 1
    """,
        (sha256,),
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_dokument_stats() -> dict:
    """Get document harvest statistics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(storlek_bytes) as total_bytes,
            SUM(CASE WHEN indexerad = 1 THEN 1 ELSE 0 END) as indexerad,
            SUM(CASE WHEN kraver_maskning = 1 THEN 1 ELSE 0 END) as flaggade
        FROM dokument
    """)
    row = cursor.fetchone()

    # Get per-kommun counts
    cursor = conn.execute("""
        SELECT kommun_kod, COUNT(*) as count
        FROM dokument
        GROUP BY kommun_kod
        ORDER BY count DESC
    """)
    per_kommun = {r[0]: r[1] for r in cursor.fetchall()}

    # Get per-type counts
    cursor = conn.execute("""
        SELECT relevans_tagg, COUNT(*) as count
        FROM dokument
        GROUP BY relevans_tagg
    """)
    per_typ = {r[0] or "unknown": r[1] for r in cursor.fetchall()}

    conn.close()

    return {
        "total_dokument": row[0] or 0,
        "total_bytes": row[1] or 0,
        "total_gb": round((row[1] or 0) / (1024**3), 2),
        "indexerade": row[2] or 0,
        "flaggade_for_maskning": row[3] or 0,
        "per_kommun": per_kommun,
        "per_dokumenttyp": per_typ,
    }


# ============================================================
# Error logging functions
# ============================================================


def log_fel(kommun_kod: str, url: str, fel_typ: str, meddelande: str):
    """Log an error for later analysis."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO fel_logg (kommun_kod, url, fel_typ, meddelande)
        VALUES (?, ?, ?, ?)
    """,
        (kommun_kod, url, fel_typ, meddelande),
    )
    conn.commit()
    conn.close()


def get_fel_summary() -> dict:
    """Get error summary by type."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT fel_typ, COUNT(*) as count
        FROM fel_logg
        GROUP BY fel_typ
        ORDER BY count DESC
    """)
    by_type = {r[0]: r[1] for r in cursor.fetchall()}

    cursor = conn.execute("""
        SELECT kommun_kod, COUNT(*) as count
        FROM fel_logg
        GROUP BY kommun_kod
        ORDER BY count DESC
        LIMIT 10
    """)
    top_kommuner = {r[0]: r[1] for r in cursor.fetchall()}

    cursor = conn.execute("SELECT COUNT(*) FROM fel_logg")
    total = cursor.fetchone()[0]

    conn.close()

    return {"total_fel": total, "per_typ": by_type, "top_kommuner_med_fel": top_kommuner}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: sqlite_state.py <command> [args]")
        print("Commands:")
        print("  init                    - Initialize database with all tables")
        print("  load <manifest.json>    - Load kommun manifest")
        print("  progress                - Show kommun progress")
        print("  failed                  - List failed kommuner")
        print("  reset                   - Reset failed kommuner to pending")
        print("  export <output.json>    - Export kommun results")
        print("  stats                   - Aggregate CMS/diarium stats")
        print("  dok-stats               - Document harvest statistics")
        print("  fel-stats               - Error log summary")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        init_db()
        print("Database initialized (kommuner, dokument, fel_logg tables)")

    elif cmd == "load":
        load_manifest(sys.argv[2])

    elif cmd == "progress":
        print(json.dumps(get_overall_progress(), indent=2))

    elif cmd == "failed":
        for task in get_failed_tasks():
            print(f"{task.id}: {task.namn} - {task.error}")

    elif cmd == "reset":
        reset_failed_tasks()

    elif cmd == "export":
        export_results(sys.argv[2])

    elif cmd == "stats":
        print(json.dumps(aggregate_stats(), indent=2, ensure_ascii=False))

    elif cmd == "dok-stats":
        print(json.dumps(get_dokument_stats(), indent=2, ensure_ascii=False))

    elif cmd == "fel-stats":
        print(json.dumps(get_fel_summary(), indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
