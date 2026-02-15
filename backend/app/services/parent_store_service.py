"""
Parent Store Service — SQLite-backed parent-child retrieval for SFS
===================================================================

Provides kapitel-level context for §-level search results. When vector search
returns individual § chunks, this service resolves their parent kapitel to give
the LLM broader context.

The SQLite DB is memory-mapped (WAL mode) and read-only at runtime, so it adds
negligible RAM overhead.

Usage:
    from app.services.parent_store_service import get_parent_store_service

    service = get_parent_store_service()
    if service.is_available():
        parents = service.resolve_parents(["1974:152_2_kap_3_§"])
"""

from __future__ import annotations

import json
import logging
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger("constitutional.parent_store")

# Default path relative to project root
_DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "parent_store" / "parents.db"


class ParentStoreService:
    """Read-only service for resolving child chunks to parent kapitel context."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection | None:
        """Lazy-load read-only connection with WAL mode."""
        if self._conn is not None:
            return self._conn

        if not self._db_path.exists():
            logger.info(f"Parent store DB not found at {self._db_path}")
            return None

        try:
            # Open read-only with URI mode
            uri = f"file:{self._db_path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            logger.info(f"Parent store connected: {self._db_path}")
            return self._conn
        except Exception as e:
            logger.warning(f"Failed to open parent store: {e}")
            return None

    def is_available(self) -> bool:
        """Check if the parent store DB exists and is accessible."""
        return self._get_conn() is not None

    def resolve_parents(self, child_chunk_ids: list[str]) -> list[dict[str, Any]]:
        """
        Resolve child chunk IDs to their parent kapitel context.

        Takes child IDs from vector search, JOINs child_parent_map -> parents,
        returns deduplicated parent context. If 3 children from same kapitel
        match, the parent is returned once.

        Args:
            child_chunk_ids: List of chunk IDs from vector search results

        Returns:
            List of parent context dicts with keys:
                parent_id, sfs_nummer, law_name, kortnamn, kapitel,
                kapitel_rubrik, full_text, child_count, references
        """
        conn = self._get_conn()
        if conn is None or not child_chunk_ids:
            return []

        # Use parameterized query with IN clause
        placeholders = ",".join("?" * len(child_chunk_ids))
        query = f"""
            SELECT DISTINCT
                p.parent_id,
                p.sfs_nummer,
                p.law_name,
                p.kortnamn,
                p.kapitel,
                p.kapitel_rubrik,
                p.full_text,
                p.child_count,
                p.references_json
            FROM child_parent_map cm
            JOIN parents p ON cm.parent_id = p.parent_id
            WHERE cm.child_chunk_id IN ({placeholders})
        """

        try:
            cursor = conn.execute(query, child_chunk_ids)
            rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Parent store query failed: {e}")
            return []

        parents = []
        for row in rows:
            refs = None
            if row["references_json"]:
                try:
                    refs = json.loads(row["references_json"])
                except json.JSONDecodeError:
                    pass

            parents.append(
                {
                    "parent_id": row["parent_id"],
                    "sfs_nummer": row["sfs_nummer"],
                    "law_name": row["law_name"],
                    "kortnamn": row["kortnamn"],
                    "kapitel": row["kapitel"],
                    "kapitel_rubrik": row["kapitel_rubrik"],
                    "full_text": row["full_text"],
                    "child_count": row["child_count"],
                    "references": refs,
                    "is_parent_context": True,
                }
            )

        if parents:
            logger.info(
                f"Parent store: resolved {len(child_chunk_ids)} children "
                f"→ {len(parents)} unique parents"
            )

        return parents

    def get_parents_by_ids(self, parent_ids: list[str]) -> list[dict[str, Any]]:
        """
        Fetch parents directly by parent_id (bypasses child_parent_map).

        Used by _expand_parent_context() which constructs parent_ids from
        ChromaDB chunk IDs, avoiding the ID format mismatch between ChromaDB
        (sfs_1974_152_2kap_3§_hash_0) and child_parent_map (1974:152_2_kap_3_§).

        Args:
            parent_ids: List of parent IDs (e.g. ["1974:152_2_kap", "1915:218_root"])

        Returns:
            List of parent context dicts (same format as resolve_parents)
        """
        conn = self._get_conn()
        if conn is None or not parent_ids:
            return []

        placeholders = ",".join("?" * len(parent_ids))
        query = f"""
            SELECT
                parent_id, sfs_nummer, law_name, kortnamn, kapitel,
                kapitel_rubrik, full_text, child_count, references_json
            FROM parents
            WHERE parent_id IN ({placeholders})
        """

        try:
            cursor = conn.execute(query, parent_ids)
            rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Parent store get_parents_by_ids failed: {e}")
            return []

        parents = []
        for row in rows:
            refs = None
            if row["references_json"]:
                try:
                    refs = json.loads(row["references_json"])
                except json.JSONDecodeError:
                    pass

            parents.append(
                {
                    "parent_id": row["parent_id"],
                    "sfs_nummer": row["sfs_nummer"],
                    "law_name": row["law_name"],
                    "kortnamn": row["kortnamn"],
                    "kapitel": row["kapitel"],
                    "kapitel_rubrik": row["kapitel_rubrik"],
                    "full_text": row["full_text"],
                    "child_count": row["child_count"],
                    "references": refs,
                    "is_parent_context": True,
                }
            )

        if parents:
            logger.info(
                f"Parent store: fetched {len(parents)} parents "
                f"by direct ID lookup ({len(parent_ids)} requested)"
            )

        return parents

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the parent store."""
        conn = self._get_conn()
        if conn is None:
            return {
                "available": False,
                "db_path": str(self._db_path),
                "parent_count": 0,
                "child_count": 0,
            }

        try:
            parent_count = conn.execute("SELECT COUNT(*) FROM parents").fetchone()[0]
            child_count = conn.execute("SELECT COUNT(*) FROM child_parent_map").fetchone()[0]
            law_count = conn.execute("SELECT COUNT(DISTINCT sfs_nummer) FROM parents").fetchone()[0]
        except Exception as e:
            logger.warning(f"Parent store stats failed: {e}")
            return {
                "available": True,
                "db_path": str(self._db_path),
                "parent_count": 0,
                "child_count": 0,
                "error": str(e),
            }

        return {
            "available": True,
            "db_path": str(self._db_path),
            "parent_count": parent_count,
            "child_count": child_count,
            "law_count": law_count,
            "db_size_mb": round(self._db_path.stat().st_size / (1024 * 1024), 2),
        }

    def close(self):
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


@lru_cache(maxsize=1)
def get_parent_store_service() -> ParentStoreService:
    """Singleton factory for ParentStoreService."""
    return ParentStoreService()
