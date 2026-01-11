"""
Reranking Service - BGE Cross-Encoder Wrapper
Wrapper for BGE reranker-v2-m3 cross-encoder model
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
    Configuration for BGE reranker service.
    """

    model: str = "BAAI/bge-reranker-v2-m3"
    max_length: int = 512
    batch_size: int = 16
    device: str = "cuda"  # or 'cpu'


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
    Reranking Service - BGE cross-encoder wrapper.

    Features:
    - Cross-encoder reranking (query, doc) pairs
    - Batch processing for efficiency
    - VRAM management (model loading/unloading)
    - Score normalization and calibration

    Model Info:
    - BGE reranker-v2-m3
    - ~1.2GB VRAM when loaded
    - Latency: ~10-30ms per batch
    - Max length: 512 tokens
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
        Load BGE reranker model (lazy loading).

        Only called on first reranking operation.
        Falls back to CPU if CUDA is out of memory.
        """
        if self._is_loaded:
            return

        try:
            import torch
            from sentence_transformers import CrossEncoder

            self.logger.info(f"Loading BGE reranker model: {self.config.reranking_model}")

            # Try CUDA first
            device = "cuda" if torch.cuda.is_available() else "cpu"
            try:
                # Load cross-encoder on CUDA
                self._model = CrossEncoder(
                    self.config.reranking_model,
                    max_length=512,
                    device=device,
                    trust_remote_code=True,
                )
                self._is_loaded = True
                self.logger.info(f"BGE reranker model loaded on {device} (~1.2GB VRAM)")
            except RuntimeError as e:
                # Check if CUDA OOM error
                if "out of memory" in str(e).lower() or "cuda" in str(e).lower():
                    self.logger.warning(f"CUDA OOM when loading reranker, falling back to CPU: {e}")
                    # Clear CUDA cache
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    # Load on CPU instead
                    self._model = CrossEncoder(
                        self.config.reranking_model,
                        max_length=512,
                        device="cpu",
                        trust_remote_code=True,
                    )
                    self._is_loaded = True
                    self.logger.info("BGE reranker model loaded on CPU (fallback)")
                else:
                    raise

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
            max_length=512,
            batch_size=16,
            device="cuda",
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
            self.logger.info("Unloading BGE reranker model")
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
        Rerank documents for a query using BGE cross-encoder.

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
            # BGE format: list of (query, passage) tuples
            pairs = list(zip([query] * len(documents), doc_texts))

            self.logger.info(f"Reranking {len(documents)} documents for query: '{query[:50]}...'")

            # Run inference in executor (blocking call)
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None,
                self._model.predict,
                pairs,
            )

            # Normalize scores (sigmoid-like transformation)
            # BGE outputs logits, convert to 0-1 range
            import numpy as np

            normalized_scores = 1 / (1 + np.exp(-np.array(scores)))

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Sort by new scores (highest first)
            scored_docs = list(zip(documents, normalized_scores.tolist()))
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
