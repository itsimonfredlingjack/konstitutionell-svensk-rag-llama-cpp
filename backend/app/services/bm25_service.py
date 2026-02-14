"""
BM25 Sidecar Service - Lexical Search with SQLite FTS5
======================================================

Provides BM25 keyword search alongside ChromaDB dense retrieval for hybrid search.
Uses SQLite FTS5 (disk-based, WAL mode) for zero-dependency sparse retrieval.

Key features:
- Disk-based: No RAM bloat (~0 MB resident vs ~3.8 GB with retriv)
- WAL mode: Concurrent readers from async executor
- Lazy loading: DB opened on first search
- Swedish-aware: unicode61 tokenizer with diacritics removal
- Compound splitting: Expands Swedish compound words for better recall

Usage:
    bm25_service = get_bm25_service()
    results = bm25_service.search("tryckfrihetsförordningen", k=50)
"""

import logging
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .swedish_compound_splitter import get_compound_splitter

logger = logging.getLogger("constitutional.bm25")

# Default paths
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "bm25_fts5" / "bm25.db"

# FTS5 reserved words that must be stripped from user queries
_FTS5_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR"})

# Characters that break FTS5 query syntax
_FTS5_STRIP_RE = re.compile(r'["\'\(\)\*\^:{}[\]~]')


def _sanitize_fts_query(query: str) -> str:
    """
    Sanitize a query string for safe FTS5 MATCH usage.

    Strips FTS5 operators and special characters, then joins tokens
    with OR (FTS5 defaults to AND for space-separated terms, but
    compound-expanded queries need OR semantics).

    Args:
        query: Raw query string (possibly compound-expanded)

    Returns:
        FTS5-safe query string like '"tok1" OR "tok2" OR "tok3"'
    """
    if not query or not query.strip():
        return ""

    # Strip special characters
    cleaned = _FTS5_STRIP_RE.sub(" ", query)

    # Tokenize and filter
    tokens = []
    for token in cleaned.split():
        token = token.strip()
        if not token:
            continue
        if token.upper() in _FTS5_RESERVED:
            continue
        tokens.append(token)

    if not tokens:
        return ""

    # Quote each token and join with OR
    return " OR ".join(f'"{t}"' for t in tokens)


class BM25Service:
    """
    Sidecar BM25 service for lexical search.

    Opens a pre-built SQLite FTS5 database and provides search functionality
    that integrates with the existing RAG-Fusion pipeline.
    """

    def __init__(
        self,
        index_path: Optional[str] = None,
        stemmer: str = "swedish",
        min_df: int = 1,
        threads: Optional[int] = None,
    ):
        """
        Initialize BM25 service.

        Args:
            index_path: Path to FTS5 database file (default: data/bm25_fts5/bm25.db)
            stemmer: Kept for API compat (unused by FTS5)
            min_df: Kept for API compat (unused by FTS5)
            threads: Kept for API compat (unused by FTS5)
        """
        self.index_path = Path(index_path) if index_path else DEFAULT_DB_PATH
        self.stemmer = stemmer
        self.min_df = min_df
        self.threads = threads or 4
        self._conn: Optional[sqlite3.Connection] = None
        self._is_loaded = False
        self._doc_count = 0

        # Initialize compound splitter for query expansion
        self._compound_splitter = get_compound_splitter()
        if self._compound_splitter.is_available():
            logger.info(f"BM25Service initialized with compound splitting (db: {self.index_path})")
        else:
            logger.info(
                f"BM25Service initialized without compound splitting (db: {self.index_path})"
            )

    def _ensure_loaded(self) -> bool:
        """
        Ensure FTS5 database is open. Lazy loading on first search.

        Returns:
            True if database is open, False if not available
        """
        if self._is_loaded:
            return True

        if not self.index_path.exists():
            logger.warning(f"BM25 FTS5 database not found at {self.index_path}")
            return False

        try:
            logger.info(f"Opening BM25 FTS5 database from {self.index_path}...")
            start = time.perf_counter()

            self._conn = sqlite3.connect(
                str(self.index_path),
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap

            # Verify table exists
            cursor = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='docs_fts'"
            )
            if cursor.fetchone() is None:
                logger.error("FTS5 table 'docs_fts' not found in database")
                self._conn.close()
                self._conn = None
                return False

            # Get doc count
            cursor = self._conn.execute("SELECT count(*) FROM docs_fts")
            self._doc_count = cursor.fetchone()[0]

            self._is_loaded = True
            load_time = time.perf_counter() - start
            logger.info(f"BM25 FTS5 database opened: {self._doc_count:,} docs in {load_time:.2f}s")
            return True

        except Exception as e:
            logger.error(f"Failed to open BM25 FTS5 database: {e}")
            if self._conn:
                self._conn.close()
                self._conn = None
            return False

    def search(
        self,
        query: str,
        k: int = 50,
        return_docs: bool = False,
        use_compound_splitting: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search documents using BM25 via FTS5.

        Args:
            query: Search query (will be tokenized by FTS5 unicode61)
            k: Number of results to return
            return_docs: Include full document text in results
            use_compound_splitting: Enable Swedish compound word expansion (default: True)

        Returns:
            List of dicts with keys: id, score, (optionally: text, metadata)
            Format compatible with RRF fusion
        """
        if not self._ensure_loaded():
            logger.debug("BM25 FTS5 database not available, returning empty results")
            return []

        if not query or not query.strip():
            return []

        try:
            start = time.perf_counter()

            # Expand compound words in query for better recall
            expanded_query = query
            if (
                use_compound_splitting
                and self._compound_splitter
                and self._compound_splitter.is_available()
            ):
                expanded_query = self._compound_splitter.expand_text(query)
                if expanded_query != query:
                    logger.debug(f"Query expanded: '{query}' → '{expanded_query}'")

            # Sanitize for FTS5
            fts_query = _sanitize_fts_query(expanded_query)
            if not fts_query:
                return []

            # Build SQL — negate bm25() because FTS5 returns negative scores
            if return_docs:
                sql = (
                    "SELECT doc_id, -bm25(docs_fts) AS score, content "
                    "FROM docs_fts WHERE docs_fts MATCH ? "
                    "ORDER BY score DESC LIMIT ?"
                )
            else:
                sql = (
                    "SELECT doc_id, -bm25(docs_fts) AS score "
                    "FROM docs_fts WHERE docs_fts MATCH ? "
                    "ORDER BY score DESC LIMIT ?"
                )

            cursor = self._conn.execute(sql, (fts_query, k))
            rows = cursor.fetchall()

            latency_ms = (time.perf_counter() - start) * 1000

            results = []
            for row in rows:
                result = {
                    "id": row[0],
                    "score": float(row[1]),
                    "source": "bm25",
                }
                if return_docs and len(row) > 2:
                    result["text"] = row[2] or ""
                results.append(result)

            logger.debug(
                f"BM25 search: '{query[:30]}...' → {len(results)} results in {latency_ms:.1f}ms"
            )

            return results

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def get_doc_scores(
        self,
        query: str,
        doc_ids: List[str],
    ) -> Dict[str, float]:
        """
        Get BM25 scores for specific documents (for reranking).

        Args:
            query: Search query
            doc_ids: List of document IDs to score

        Returns:
            Dict mapping doc_id to BM25 score
        """
        if not self._ensure_loaded() or not doc_ids:
            return {}

        if not query or not query.strip():
            return {}

        try:
            # Expand and sanitize query
            expanded_query = query
            if self._compound_splitter and self._compound_splitter.is_available():
                expanded_query = self._compound_splitter.expand_text(query)

            fts_query = _sanitize_fts_query(expanded_query)
            if not fts_query:
                return {}

            # SQLite supports up to 999 params; typical usage is 10-100 doc_ids
            placeholders = ",".join("?" for _ in doc_ids)
            sql = (
                f"SELECT doc_id, -bm25(docs_fts) AS score "
                f"FROM docs_fts WHERE docs_fts MATCH ? AND doc_id IN ({placeholders})"
            )
            params = [fts_query] + list(doc_ids)

            cursor = self._conn.execute(sql, params)
            return {row[0]: float(row[1]) for row in cursor.fetchall()}

        except Exception as e:
            logger.error(f"BM25 get_doc_scores failed: {e}")
            return {}

    def is_available(self) -> bool:
        """Check if BM25 FTS5 database file exists."""
        return self.index_path.exists()

    def is_loaded(self) -> bool:
        """Check if BM25 FTS5 database is currently open."""
        return self._is_loaded

    def get_stats(self) -> Dict[str, Any]:
        """Get BM25 index statistics."""
        return {
            "available": self.is_available(),
            "loaded": self._is_loaded,
            "index_path": str(self.index_path),
            "doc_count": self._doc_count,
            "stemmer": self.stemmer,
            "threads": self.threads,
            "backend": "sqlite_fts5",
        }

    def unload(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._is_loaded = False
            self._doc_count = 0
            logger.info("BM25 FTS5 database closed")


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESSOR
# ═══════════════════════════════════════════════════════════════════════════


@lru_cache()
def get_bm25_service(
    index_path: Optional[str] = None,
) -> BM25Service:
    """
    Get singleton BM25Service instance.

    Args:
        index_path: Optional override for database path

    Returns:
        Cached BM25Service singleton instance
    """
    return BM25Service(index_path=index_path)
