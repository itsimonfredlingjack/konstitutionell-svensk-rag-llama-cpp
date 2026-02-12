"""
Reranking Service - Jina Reranker v2 Cross-Encoder Wrapper
Wrapper for Jina reranker-v2-base-multilingual cross-encoder model
"""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

from ..core.exceptions import RerankingError
from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service

logger = get_logger(__name__)


@dataclass
class RerankingConfig:
    """
    Configuration for Jina Reranker v2 service.
    """

    model: str = "jinaai/jina-reranker-v2-base-multilingual"
    max_length: int = 1024  # Jina supports 1024 tokens (upgraded from 512)
    batch_size: int = 16
    device: str = "cpu"  # GPU exclusively reserved for LLM


@dataclass
class RerankingResult:
    """
    Result of reranking operation.

    Attributes:
        original_docs: Original documents before reranking
        reranked_docs: Documents after reranking (sorted by new scores)
        original_scores: Original relevance scores (from embedding similarity)
        reranked_scores: New relevance scores (from cross-encoder)
        latency_ms: Time taken for reranking
    """

    original_docs: List[dict]
    reranked_docs: List[dict]
    original_scores: List[float]
    reranked_scores: List[float]
    latency_ms: float


class RerankingService(BaseService):
    """
    Reranking Service - Jina Reranker v2 cross-encoder wrapper.

    Features:
    - Cross-encoder reranking (query, doc) pairs
    - Batch processing for efficiency
    - CPU-only (GPU reserved for LLM)
    - Scores are pre-normalized (0-1 range, no sigmoid needed)

    Model Info:
    - jinaai/jina-reranker-v2-base-multilingual (XLM-RoBERTa, 278M params)
    - ~0.6GB RAM when loaded on CPU
    - Latency: ~10-30ms per batch
    - Max length: 1024 tokens
    - License: CC-BY-NC-4.0
    """

    # Global model cache (lazy-loaded)
    _reranker_model = None
    _model_config: Optional[RerankingConfig] = None

    def __init__(self, config: ConfigService):
        """
        Initialize Reranking Service.

        Args:
            config: ConfigService for configuration access
        """
        super().__init__(config)
        self._model = None
        self._is_loaded = False
        self.logger.info(f"Reranking Service initialized (model: {config.reranking_model})")

    def _load_model(self) -> None:
        """
        Load Jina reranker model (lazy loading).

        Only called on first reranking operation.
        Always loads on CPU to keep GPU free for LLM.
        """
        if self._is_loaded:
            return

        try:
            from sentence_transformers import CrossEncoder

            self.logger.info(f"Loading Jina reranker model: {self.config.reranking_model}")

            self._model = CrossEncoder(
                self.config.reranking_model,
                max_length=1024,
                device="cpu",
                trust_remote_code=True,
                automodel_args={"torch_dtype": "auto"},
            )
            self._is_loaded = True
            self.logger.info("Jina reranker model loaded on CPU (~0.6GB RAM)")

        except Exception as e:
            self.logger.error(f"Failed to load reranker: {e}")
            raise RerankingError(f"Failed to load reranker: {str(e)}")

    async def initialize(self) -> None:
        """
        Initialize reranking service.

        Loads model config from ConfigService.
        Model is lazy-loaded on first reranking operation.
        """
        # Load config
        self._model_config = RerankingConfig(
            model=self.config.reranking_model,
            max_length=1024,
            batch_size=16,
            device="cpu",
        )

        self._mark_initialized()

    async def health_check(self) -> bool:
        """
        Check if reranking service is healthy.

        Returns:
            True if service is initialized, False otherwise
        """
        return self._is_loaded  # Only loaded if we've attempted

    async def close(self) -> None:
        """
        Unload reranker model to free VRAM.

        Clears the singleton, so next rerank() will reload model.
        """
        if self._model is not None:
            self.logger.info("Unloading Jina reranker model")
            del self._model
            self._model = None
            self._is_loaded = False

        self._mark_uninitialized()

    async def ensure_initialized(self) -> None:
        """
        Ensure service is initialized.

        Raises:
            ServiceNotInitializedError: If service is not initialized
        """
        super().ensure_initialized()

        # Lazy-load model if not already loaded
        if not self._is_loaded:
            self._load_model()

    async def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: Optional[int] = None,
    ) -> RerankingResult:
        """
        Rerank documents for a query using Jina cross-encoder.

        Scores each (query, document) pair and sorts by score.

        Args:
            query: The search query
            documents: List of document dictionaries with 'id', 'title', 'snippet', 'score'
            top_k: Number of results to return (default: all)

        Returns:
            RerankingResult with reranked documents and scores

        Raises:
            RerankingError: If reranking fails
            ServiceNotInitializedError: If service is not initialized
        """
        await self.ensure_initialized()

        if not documents:
            self.logger.warning("No documents to rerank")
            return RerankingResult(
                original_docs=documents,
                reranked_docs=documents,
                original_scores=[],
                reranked_scores=[],
                latency_ms=0.0,
            )

        import time

        start_time = time.perf_counter()

        try:
            # Extract document IDs and texts
            doc_texts = [f"{doc.get('title', '')}\n{doc.get('snippet', '')}" for doc in documents]
            original_scores = [doc.get("score", 0.0) for doc in documents]

            # Create (query, doc) pairs for cross-encoder
            pairs = list(zip([query] * len(documents), doc_texts))

            self.logger.info(f"Reranking {len(documents)} documents for query: '{query[:50]}...'")

            # Run inference in executor (blocking call)
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None,
                self._model.predict,
                pairs,
            )

            # Jina returns pre-normalized scores (0-1 range), no sigmoid needed
            normalized_scores = list(scores)

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Sort by new scores (highest first)
            scored_docs = list(zip(documents, normalized_scores))
            scored_docs.sort(key=lambda x: -x[1])  # Sort by score descending

            # Extract reranked results
            reranked_docs = [doc for doc, _ in scored_docs]
            reranked_scores = [score for _, score in scored_docs]

            # Apply top_k limit
            if top_k and top_k < len(reranked_docs):
                reranked_docs = reranked_docs[:top_k]
                reranked_scores = reranked_scores[:top_k]

            top_score = reranked_scores[0] if reranked_scores else 0.0
            self.logger.info(
                f"Reranking complete: {len(reranked_docs)} docs in {latency_ms:.1f}ms (top: {top_score:.4f})"
            )

            return RerankingResult(
                original_docs=documents,
                reranked_docs=reranked_docs,
                original_scores=original_scores,
                reranked_scores=reranked_scores,
                latency_ms=latency_ms,
            )

        except Exception as e:
            self.logger.error(f"Reranking failed: {e}")
            raise RerankingError(f"Reranking failed: {str(e)}")

    async def rerank_batch(
        self,
        queries: List[Tuple[str, List[dict]]],
        top_k: Optional[int] = None,
    ) -> List[RerankingResult]:
        """
        Batch rerank multiple (query, documents) pairs.

        Useful for multi-query retrieval (RAG-Fusion).
        Processes all queries in parallel for efficiency.

        Args:
            queries: List of (query, documents) tuples
            top_k: Number of results to return per query (default: all)

        Returns:
            List of RerankingResult (one per query)
        """
        await self.ensure_initialized()

        if not queries:
            return []

        results = []

        # Process all queries in parallel
        tasks = [self.rerank(query, docs, top_k) for query, docs in queries]

        # Run all reranking operations in parallel
        rerank_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and collect results
        for i, result in enumerate(rerank_results):
            if isinstance(result, Exception):
                self.logger.error(f"Reranking failed for query {i}: {result}")
                continue
            results.append(result)

        return results

    def get_model_info(self) -> dict:
        """
        Get information about the loaded model.

        Returns:
            Dictionary with model name, status, and configuration
        """
        return {
            "model": self._model_config.model,
            "loaded": self._is_loaded,
            "max_length": self._model_config.max_length,
            "device": self._model_config.device,
        }


# Dependency injection function for FastAPI


@lru_cache()
def get_reranking_service(config: Optional[ConfigService] = None) -> RerankingService:
    """
    Get singleton RerankingService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Cached RerankingService instance
    """
    if config is None:
        config = get_config_service()

    return RerankingService(config)
