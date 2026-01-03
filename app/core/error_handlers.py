"""
Global Exception Handler - FastAPI Middleware
Maps business logic exceptions to appropriate HTTP responses
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from .exceptions import (
    ConstitutionalAIError,
    ResourceNotFoundError,
    ConfigurationError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMModelNotFoundError,
    EmbeddingError,
    RetrievalError,
    QueryClassificationError,
    SecurityViolationError,
    ValidationError,
    RerankingError,
    ServiceNotInitializedError,
)

from ..utils.logging import get_logger

logger = get_logger(__name__)


async def constitutional_exception_handler(
    request: Request, 
    exc: ConstitutionalAIError
) -> JSONResponse:
    """
    Convert custom exceptions to HTTP responses.
    
    Maps business logic exceptions to appropriate HTTP status codes.
    Separates error classification from HTTP transport.
    
    Args:
        request: FastAPI request object
        exc: ConstitutionalAI exception instance
        
    Returns:
        JSONResponse with appropriate status code and error details
    """
    logger.error(
        f"ConstitutionalAIError in {request.url.path}: {exc.__class__.__name__} - {str(exc)}"
    )
    
    if isinstance(exc, ResourceNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": str(exc),
                "type": "resource_not_found",
                "status_code": 404
            }
        )
    
    elif isinstance(exc, ConfigurationError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "configuration_error",
                "status_code": 500
            }
        )
    
    elif isinstance(exc, ServiceNotInitializedError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": str(exc),
                "type": "service_not_initialized",
                "status_code": 503
            }
        )
    
    elif isinstance(exc, LLMTimeoutError):
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "error": str(exc),
                "type": "llm_timeout",
                "status_code": 504
            }
        )
    
    elif isinstance(exc, LLMConnectionError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": str(exc),
                "type": "llm_connection_error",
                "status_code": 503
            }
        )
    
    elif isinstance(exc, LLMModelNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={
                "error": str(exc),
                "type": "llm_model_not_found",
                "status_code": 501
            }
        )
    
    elif isinstance(exc, SecurityViolationError):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": str(exc),
                "type": "security_violation",
                "status_code": 403
            }
        )
    
    elif isinstance(exc, ValidationError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": str(exc),
                "type": "validation_error",
                "status_code": 400
            }
        )
    
    elif isinstance(exc, EmbeddingError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "embedding_error",
                "status_code": 500
            }
        )
    
    elif isinstance(exc, RetrievalError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "retrieval_error",
                "status_code": 500
            }
        )
    
    elif isinstance(exc, QueryClassificationError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "query_classification_error",
                "status_code": 500
            }
        )
    
    elif isinstance(exc, RerankingError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "reranking_error",
                "status_code": 500
            }
        )
    
    # Default fallback for unexpected ConstitutionalAIError
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": "internal_error",
                "status_code": 500
            }
        )


def register_exception_handlers(app) -> None:
    """
    Register all custom exception handlers with FastAPI app.
    
    Should be called in main.py after app creation.
    
    Args:
        app: FastAPI application instance
    """
    # Register handler for base exception (catches all custom exceptions)
    app.add_exception_handler(
        ConstitutionalAIError, 
        constitutional_exception_handler
    )
    
    logger.info("Exception handlers registered for ConstitutionalAIError")

