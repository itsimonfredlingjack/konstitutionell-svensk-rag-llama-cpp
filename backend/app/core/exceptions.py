"""
Custom Exceptions for Constitutional AI
Separates business logic errors from HTTP transport layer
"""


class ConstitutionalAIError(Exception):
    """
    Base exception for all Constitutional AI errors.

    All custom exceptions should inherit from this.
    """

    pass


class ResourceNotFoundError(ConstitutionalAIError):
    """
    Resource (document, model, collection, etc.) not found.

    HTTP equivalent: 404 Not Found
    """

    pass


class ConfigurationError(ConstitutionalAIError):
    """
    Invalid configuration or missing required settings.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class LLMTimeoutError(ConstitutionalAIError):
    """
    LLM generation timed out.

    HTTP equivalent: 504 Gateway Timeout
    """

    pass


class LLMConnectionError(ConstitutionalAIError):
    """
    Could not connect to LLM service (Ollama).

    HTTP equivalent: 503 Service Unavailable
    """

    pass


class LLMModelNotFoundError(ConstitutionalAIError):
    """
    Requested LLM model not available/downloaded.

    HTTP equivalent: 501 Not Implemented
    """

    pass


class EmbeddingError(ConstitutionalAIError):
    """
    Embedding generation failed.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class RetrievalError(ConstitutionalAIError):
    """
    Document retrieval failed (ChromaDB error, timeout, etc.).

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class QueryClassificationError(ConstitutionalAIError):
    """
    Could not classify query mode.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class SecurityViolationError(ConstitutionalAIError):
    """
    Jail Warden detected a security violation.

    HTTP equivalent: 403 Forbidden
    """

    pass


class ValidationError(ConstitutionalAIError):
    """
    Input validation failed (invalid query, bad parameters, etc.).

    HTTP equivalent: 400 Bad Request
    """

    pass


class RerankingError(ConstitutionalAIError):
    """
    Reranking (BGE cross-encoder) failed.

    HTTP equivalent: 500 Internal Server Error
    """

    pass


class ServiceNotInitializedError(ConstitutionalAIError):
    """
    Service not properly initialized (model not loaded, connection not established, etc.).

    HTTP equivalent: 503 Service Unavailable
    """

    pass
