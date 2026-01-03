"""
Embedding Service - Singleton KBLab Swedish BERT Wrapper
Manages KBLab sentence-transformer model with lazy loading
"""

from typing import List, Optional
from functools import lru_cache

from sentence_transformers import SentenceTransformer
import numpy as np

from .config_service import ConfigService, get_config_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Singleton service for KBLab Swedish BERT embedding model.
    
    Features:
    - Lazy loading (loads on first use)
    - Singleton pattern (one model instance)
    - Dimension validation (verifies 768-dim output)
    - Batch embedding support
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
        logger.info(f"EmbeddingService initialized (model: {config.embedding_model})")
    
    def _load_model(self) -> None:
        """
        Load KBLab Swedish BERT model (lazy loading).
        
        Only called on first embedding operation.
        """
        if self._is_loaded:
            return
        
        try:
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            self._model = SentenceTransformer(self.config.embedding_model)
            
            # Verify dimension on load
            test_text = ["test"]
            test_embedding = self._model.encode(test_text)
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
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (768-dim)
            
        Raises:
            RuntimeError: If model fails to load or dimension mismatch
        """
        # Lazy load model if not already loaded
        if not self._is_loaded:
            self._load_model()
        
        if self._model is None:
            raise RuntimeError("Embedding model not initialized")
        
        # Generate embeddings in batch
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        
        # Convert to list of lists for JSON serialization
        return embeddings.tolist()
    
    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Convenience method that wraps embed() with single item.
        
        Args:
            text: Single text string to embed
            
        Returns:
            Single embedding vector (768-dim)
        """
        return self.embed([text])[0]
    
    async def embed_async(self, texts: List[str]) -> List[List[float]]:
        """
        Async wrapper for embedding (runs in executor).
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (768-dim)
        """
        import asyncio
        loop = asyncio.get_event_loop()
        
        # Run blocking embedding in executor
        embeddings = await loop.run_in_executor(
            None,
            self.embed,
            texts
        )
        
        return embeddings
    
    async def embed_single_async(self, text: str) -> List[float]:
        """
        Async wrapper for single text embedding.
        
        Convenience method that wraps embed_async() with single item.
        
        Args:
            text: Single text string to embed
            
        Returns:
            Single embedding vector (768-dim)
        """
        return (await self.embed_async([text]))[0]
    
    def get_dimension(self) -> int:
        """
        Get the embedding dimension (768 for KBLab BERT).
        
        Returns:
            Embedding dimension (number of floats per vector)
        """
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

