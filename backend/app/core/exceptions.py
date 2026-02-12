"""
Custom Exceptions for Constitutional AI
Separates business logic errors from HTTP transport layer with structured context.
"""

import functools
import time
from typing import Any, Callable, Dict, Optional, Type, TypeVar


class ConstitutionalAIError(Exception):
    """
    Base exception for all Constitutional AI errors.

    All custom exceptions should inherit from this.
    Carries structured context for debugging and monitoring.
    """

    def __init__(
        self,
        message: str,
        service_name: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.service_name = service_name
        self.operation = operation
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to structured dict for logging/monitoring."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "service_name": self.service_name,
            "operation": self.operation,
            "details": self.details,
        }


# ═══════════════════════════════════════════════════════════════════
# RESOURCE ERRORS
# ═══════════════════════════════════════════════════════════════════


class ResourceNotFoundError(ConstitutionalAIError):
    """
    Resource (document, model, collection, etc.) not found.

    HTTP equivalent: 404 Not Found
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION ERRORS
# ═══════════════════════════════════════════════════════════════════


class ConfigurationError(ConstitutionalAIError):
    """
    Invalid configuration or missing required settings.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class ServiceNotInitializedError(ConstitutionalAIError):
    """
    Service not properly initialized (model not loaded, connection not established, etc.).

    HTTP equivalent: 503 Service Unavailable
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# LLM ERRORS
# ═══════════════════════════════════════════════════════════════════


class LLMError(ConstitutionalAIError):
    """
    Base class for all LLM-related errors (Ollama/llama.cpp failures).

    HTTP equivalent: 500 Internal Server Error (or more specific subclass)
    """

    pass


class LLMTimeoutError(LLMError):
    """
    LLM generation timed out.

    HTTP equivalent: 504 Gateway Timeout
    """

    pass


class LLMConnectionError(LLMError):
    """
    Could not connect to LLM service (Ollama).

    HTTP equivalent: 503 Service Unavailable
    """

    pass


class LLMModelNotFoundError(LLMError):
    """
    Requested LLM model not available/downloaded.

    HTTP equivalent: 501 Not Implemented
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# RETRIEVAL ERRORS
# ═══════════════════════════════════════════════════════════════════


class RetrievalError(ConstitutionalAIError):
    """
    Document retrieval failed (ChromaDB error, search failures, timeout, etc.).

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class EmbeddingError(ConstitutionalAIError):
    """
    Embedding generation failed.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class RerankingError(ConstitutionalAIError):
    """
    Reranking (Jina cross-encoder) failed.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# INGESTION ERRORS
# ═══════════════════════════════════════════════════════════════════


class IngestionError(ConstitutionalAIError):
    """
    Document ingestion/processing failed (PDF parsing, chunking, embedding, storage).

    HTTP equivalent: 500 Internal Server Error
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# RAG PIPELINE ERRORS
# ═══════════════════════════════════════════════════════════════════


class CRAGError(ConstitutionalAIError):
    """
    CRAG (Corrective RAG) pipeline failed during grading or self-reflection.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class QueryClassificationError(ConstitutionalAIError):
    """
    Could not classify query mode.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# SECURITY ERRORS
# ═══════════════════════════════════════════════════════════════════


class SecurityViolationError(ConstitutionalAIError):
    """
    Jail Warden detected a security violation.

    HTTP equivalent: 403 Forbidden
    """

    pass


class HarmfulContentError(ConstitutionalAIError):
    """
    Harmful content detected in query.

    HTTP equivalent: 403 Forbidden
    """

    pass


class ValidationError(ConstitutionalAIError):
    """
    Input validation failed (invalid query, bad parameters, etc.).

    HTTP equivalent: 400 Bad Request
    """

    pass


# ═══════════════════════════════════════════════════════════════════
# RETRY DECORATOR
# ═══════════════════════════════════════════════════════════════════

T = TypeVar("T")


def retry_on_transient_error(
    max_attempts: int = 3,
    delay_seconds: float = 0.5,
    backoff_multiplier: float = 2.0,
    transient_exceptions: tuple[Type[Exception], ...] = (
        LLMConnectionError,
        LLMTimeoutError,
        RetrievalError,
        EmbeddingError,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry functions on transient errors with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        delay_seconds: Initial delay between retries in seconds (default: 0.5)
        backoff_multiplier: Multiply delay by this factor after each retry (default: 2.0)
        transient_exceptions: Tuple of exception types to retry on

    Usage:
        @retry_on_transient_error(max_attempts=3)
        async def fetch_embeddings(text: str):
            return await embedding_service.embed(text)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay_seconds

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except transient_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        # Final attempt failed, re-raise
                        raise

                    # Log retry attempt
                    print(f"Retry {attempt}/{max_attempts} after {e.__class__.__name__}: {e}")

                    # Wait before retry
                    time.sleep(current_delay)
                    current_delay *= backoff_multiplier

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            return None  # Type checker satisfaction

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay_seconds

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except transient_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        raise

                    print(f"Retry {attempt}/{max_attempts} after {e.__class__.__name__}: {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff_multiplier

            if last_exception:
                raise last_exception
            return None

        # Check if function is async
        if functools.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
