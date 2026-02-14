"""
BM25 Sidecar Service - Lexical Search with retriv
==================================================

Provides BM25 keyword search alongside ChromaDB dense retrieval for hybrid search.
Uses retriv (Numba-accelerated) for fast multi-threaded sparse retrieval.

Key features:
- Lazy loading: Index loaded on first search
- Memory-efficient: Uses CSR sparse matrices
- Multi-threaded: Utilizes all CPU cores
- Swedish-aware: Snowball stemmer support
- Compound splitting: Expands Swedish compound words for better recall

Usage:
    bm25_service = get_bm25_service()
    results = bm25_service.search("tryckfrihetsförordningen", k=50)
"""

import logging
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .swedish_compound_splitter import get_compound_splitter

logger = logging.getLogger("constitutional.bm25")

# Default paths
DEFAULT_INDEX_DIR = Path(__file__).parent.parent.parent.parent / "data" / "bm25_index"


class BM25Service:
    """
    Sidecar BM25 service for lexical search.

    Loads a pre-built retriv index and provides search functionality
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
            index_path: Path to retriv index directory (default: data/bm25_index)
            stemmer: Snowball stemmer language (default: swedish)
            min_df: Minimum document frequency for terms (default: 1)
            threads: Number of search threads (default: all cores)
        """
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX_DIR
        self.stemmer = stemmer
        self.min_df = min_df
        self.threads = threads or os.cpu_count() or 4
        self._search_engine = None
        self._is_loaded = False
        self._doc_count = 0

        # Initialize compound splitter for query expansion
        self._compound_splitter = get_compound_splitter()
        if self._compound_splitter.is_available():
            logger.info(
                f"BM25Service initialized with compound splitting (index_path: {self.index_path})"
            )
        else:
            logger.info(
                f"BM25Service initialized without compound splitting (index_path: {self.index_path})"
            )

    def _ensure_loaded(self) -> bool:
        """
        Ensure index is loaded. Lazy loading on first search.

        Returns:
            True if index is loaded, False if not available
        """
        if self._is_loaded:
            return True

        if not self.index_path.exists():
            logger.warning(f"BM25 index not found at {self.index_path}")
            return False

        try:
            import retriv

            logger.info(f"Loading BM25 index from {self.index_path}...")
            start = time.perf_counter()

            self._search_engine = retriv.SparseRetriever.load(str(self.index_path))
            self._is_loaded = True

            # Get doc count if available
            try:
                # retriv exposes doc count on the retriever object (preferred).
                # Older implementations may expose it on the underlying index.
                self._doc_count = int(getattr(self._search_engine, "doc_count", 0) or 0)
                if not self._doc_count and getattr(self._search_engine, "index", None) is not None:
                    self._doc_count = int(getattr(self._search_engine.index, "n_docs", 0) or 0)
            except Exception:
                self._doc_count = 0

            load_time = time.perf_counter() - start
            logger.info(f"BM25 index loaded: {self._doc_count:,} docs in {load_time:.2f}s")
            return True

        except Exception as e:
            logger.error(f"Failed to load BM25 index: {e}")
            return False

    def search(
        self,
        query: str,
        k: int = 50,
        return_docs: bool = False,
        use_compound_splitting: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search documents using BM25.

        Args:
            query: Search query (will be processed with stemmer)
            k: Number of results to return
            return_docs: Include full document text in results
            use_compound_splitting: Enable Swedish compound word expansion (default: True)

        Returns:
            List of dicts with keys: id, score, (optionally: text, metadata)
            Format compatible with RRF fusion
        """
        if not self._ensure_loaded():
            logger.debug("BM25 index not available, returning empty results")
            return []

        if not query or not query.strip():
            return []

        try:
            start = time.perf_counter()

            # Expand compound words in query for better recall
            # "skadeståndsanspråk" → "skadeståndsanspråk skadestånd anspråk"
            expanded_query = query
            if (
                use_compound_splitting
                and self._compound_splitter
                and self._compound_splitter.is_available()
            ):
                expanded_query = self._compound_splitter.expand_text(query)
                if expanded_query != query:
                    logger.debug(f"Query expanded: '{query}' → '{expanded_query}'")

            # retriv returns list of dicts: [{id, text, score}, ...]
            raw_results = self._search_engine.search(
                query=expanded_query,
                cutoff=k,
            )

            latency_ms = (time.perf_counter() - start) * 1000

            # Convert to format compatible with RRF
            results = []
            for doc in raw_results:
                result = {
                    "id": doc.get("id", ""),
                    "score": float(doc.get("score", 0.0)),
                    "source": "bm25",
                }

                # Optionally include document text
                if return_docs:
                    result["text"] = doc.get("text", "")

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

        try:
            # Get all results up to reasonable limit
            all_results = self.search(query, k=min(len(doc_ids) * 10, 1000))

            # Filter to requested IDs
            scores = {}
            for result in all_results:
                if result["id"] in doc_ids:
                    scores[result["id"]] = result["score"]

            return scores

        except Exception as e:
            logger.error(f"BM25 get_doc_scores failed: {e}")
            return {}

    def is_available(self) -> bool:
        """Check if BM25 index is available and can be loaded."""
        return self.index_path.exists()

    def is_loaded(self) -> bool:
        """Check if BM25 index is currently loaded in memory."""
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
        }

    def unload(self) -> None:
        """Unload index from memory."""
        if self._search_engine is not None:
            del self._search_engine
            self._search_engine = None
            self._is_loaded = False
            self._doc_count = 0
            logger.info("BM25 index unloaded")


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
        index_path: Optional override for index path

    Returns:
        Cached BM25Service singleton instance
    """
    return BM25Service(index_path=index_path)
