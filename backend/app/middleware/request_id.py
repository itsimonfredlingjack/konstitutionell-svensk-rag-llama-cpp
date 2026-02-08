"""
Request ID Middleware
Generates and attaches unique request IDs to all requests for distributed tracing
"""

import uuid
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from contextvars import ContextVar

# Context variable for request ID (thread-safe)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates a unique request ID for each request.

    The request ID is:
    - Extracted from X-Request-ID header if present
    - Otherwise generated as a new UUID
    - Stored in context variable for access in logging
    - Added to response headers
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate request ID
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in context variable
        request_id_var.set(request_id)

        # Attach to request state for FastAPI access
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response


def get_request_id() -> str:
    """
    Get the current request ID from context.

    Returns:
        Current request ID or empty string if not in request context
    """
    return request_id_var.get()
