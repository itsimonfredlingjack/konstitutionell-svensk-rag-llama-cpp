"""
Embedding Service - Singleton SentenceTransformer Wrapper

Manages sentence-transformer embedding model with lazy loading.
Supports asymmetric encoding via task-specific LoRA adapters (Jina v3):
  - embed_query()    → task="retrieval.query"   (for search queries)
  - embed_document() → task="retrieval.passage"  (for document indexing)
"""

from functools import lru_cache
from typing import List, Optional

from sentence_transformers import SentenceTransformer

from ..utils.logging import get_logger
from .config_service import ConfigService, get_config_service

logger = get_logger(__name__)

# Jina v3 task identifiers for asymmetric encoding
_TASK_QUERY = "retrieval.query"
_TASK_PASSAGE = "retrieval.passage"


class EmbeddingService:
    """
    Singleton service for sentence-transformer embedding models.

    Features:
    - Lazy loading (loads on first use)
    - Singleton pattern (one model instance)
    - Dimension validation (verifies expected output)
    - Batch embedding support
    - Asymmetric encoding (query vs document) for Jina v3
    """

    _instance: Optional["EmbeddingService"] = None

    def __new__(cls, config: ConfigService):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: ConfigService):
        """
        Initialize Embedding Service.

        Note: Model is lazy-loaded on first call to embed()
        """
        self.config = config
        self._model: Optional[SentenceTransformer] = None
        self._is_loaded: bool = False
        self._supports_task: bool = "jina" in config.embedding_model.lower()
        logger.info(f"EmbeddingService initialized (model: {config.embedding_model})")

    def _load_model(self) -> None:
        """
        Load embedding model (lazy loading).

        Only called on first embedding operation.
        """
        if self._is_loaded:
            return

        try:
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            # Force CPU to save VRAM for the LLM
            try:
                self._model = SentenceTransformer(
                    self.config.embedding_model,
                    device="cpu",
                    trust_remote_code=True,
                )
            except TypeError:
                # Older sentence-transformers versions may not support trust_remote_code.
                self._model = SentenceTransformer(self.config.embedding_model, device="cpu")

            # Verify dimension on load (use query task for Jina v3)
            test_text = ["test"]
            encode_kwargs = {"convert_to_numpy": True, "show_progress_bar": False}
            if self._supports_task:
                encode_kwargs["task"] = _TASK_QUERY
            test_embedding = self._model.encode(test_text, **encode_kwargs)
            actual_dim = test_embedding.shape[-1]
            expected_dim = self.config.expected_embedding_dim

            if actual_dim != expected_dim:
                raise RuntimeError(
                    f"FATAL: Embedding dimension mismatch! "
                    f"Expected {expected_dim}, got {actual_dim}"
                )

            self._is_loaded = True
            logger.info(f"Embedding model loaded: {actual_dim}-dim ✓")

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    # ─── Internal task-aware encoding ────────────────────────────────

    def _encode(self, texts: List[str], task: Optional[str] = None) -> List[List[float]]:
        """
        Internal encoding method with optional task parameter.

        For Jina v3, the task parameter activates the appropriate LoRA adapter:
        - "retrieval.query" for search queries
        - "retrieval.passage" for document passages

        Args:
            texts: List of text strings to encode
            task: Optional task identifier for asymmetric encoding

        Returns:
            List of embedding vectors
        """
        if not self._is_loaded:
            self._load_model()

        if self._model is None:
            raise RuntimeError("Embedding model not initialized")

        encode_kwargs = {"convert_to_numpy": True, "show_progress_bar": False}
        if task and self._supports_task:
            encode_kwargs["task"] = task

        embeddings = self._model.encode(texts, **encode_kwargs)
        return embeddings.tolist()

    # ─── Public API: asymmetric encoding ─────────────────────────────

    def embed_query(self, texts: List[str]) -> List[List[float]]:
        """
        Generate query embeddings (retrieval.query task).

        Use this for search queries. For Jina v3, this activates the
        query-optimized LoRA adapter.

        Args:
            texts: List of query strings

        Returns:
            List of embedding vectors
        """
        return self._encode(texts, task=_TASK_QUERY)

    def embed_document(self, texts: List[str]) -> List[List[float]]:
        """
        Generate document embeddings (retrieval.passage task).

        Use this for indexing documents. For Jina v3, this activates the
        passage-optimized LoRA adapter.

        Args:
            texts: List of document strings

        Returns:
            List of embedding vectors
        """
        return self._encode(texts, task=_TASK_PASSAGE)

    def embed_single_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query text.

        Args:
            text: Single query string

        Returns:
            Single embedding vector
        """
        return self.embed_query([text])[0]

    async def embed_document_async(self, texts: List[str]) -> List[List[float]]:
        """
        Async wrapper for document embedding (runs in executor).

        Args:
            texts: List of document strings

        Returns:
            List of embedding vectors
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_document, texts)

    # ─── Backward-compatible aliases ─────────────────────────────────

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Alias for embed_query() — all existing callers embed queries.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        return self.embed_query(texts)

    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Alias for embed_single_query().

        Args:
            text: Single text string to embed

        Returns:
            Single embedding vector
        """
        return self.embed_single_query(text)

    async def embed_async(self, texts: List[str]) -> List[List[float]]:
        """
        Async wrapper for query embedding (runs in executor).

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, texts)

    async def embed_single_async(self, text: str) -> List[float]:
        """
        Async wrapper for single text query embedding.

        Args:
            text: Single text string to embed

        Returns:
            Single embedding vector
        """
        return (await self.embed_async([text]))[0]

    # ─── Utility methods ─────────────────────────────────────────────

    def get_dimension(self) -> int:
        """Get the embedding dimension configured for this model."""
        return self.config.expected_embedding_dim

    def is_loaded(self) -> bool:
        """
        Check if the embedding model is loaded.

        Returns:
            True if model is loaded, False otherwise
        """
        return self._is_loaded

    def unload(self) -> None:
        """
        Unload the embedding model to free memory.

        Note: This clears the singleton, so next embed() will reload model.
        """
        if self._model is not None:
            del self._model
            self._model = None
            self._is_loaded = False
            logger.info("Embedding model unloaded")


@lru_cache()
def get_embedding_service(config: Optional[ConfigService] = None) -> EmbeddingService:
    """
    Get singleton EmbeddingService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Cached EmbeddingService singleton instance
    """
    if config is None:
        config = get_config_service()

    return EmbeddingService(config)


# Global instance for backward compatibility
embedding_service = get_embedding_service()
