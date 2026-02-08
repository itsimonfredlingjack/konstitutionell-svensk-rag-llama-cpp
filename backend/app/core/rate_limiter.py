"""
Rate Limiting — Request throttling for Constitutional AI API.

Uses slowapi (built on limits + starlette).
Configure via CONST_RATE_LIMIT_* environment variables.
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..utils.logging import get_logger

logger = get_logger(__name__)


def _key_func(request: Request) -> str:
    """Extract client identifier for rate limiting (IP-based)."""
    return get_remote_address(request)


# Global limiter instance — imported by route modules
limiter = Limiter(key_func=_key_func)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom handler for rate limit exceeded errors."""
    logger.warning(f"Rate limit exceeded: {request.client.host} on {request.url.path}")
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded. Please try again later.",
            "type": "rate_limit_exceeded",
            "retry_after": exc.detail,
        },
    )
