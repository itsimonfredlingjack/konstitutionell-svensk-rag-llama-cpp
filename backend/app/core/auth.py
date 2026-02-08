"""
Simple API key authentication for write operations.

Usage:
    @router.post("/endpoint")
    async def endpoint(api_key: str = Depends(require_write_access)):
        ...

Configure via environment variable:
    CONST_API_KEY=your-secret-key

If CONST_API_KEY is not set, write operations are open (development mode).
"""

import os
from typing import Optional

from fastapi import Header, HTTPException, status


def _get_configured_api_key() -> Optional[str]:
    """Get the configured API key from environment."""
    return os.environ.get("CONST_API_KEY")


async def require_write_access(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """
    Dependency that requires a valid API key for write operations.

    If CONST_API_KEY is not configured, all requests are allowed (dev mode).
    If configured, requests must include a matching X-API-Key header.
    """
    configured_key = _get_configured_api_key()

    if configured_key is None:
        # No API key configured — open access (development mode)
        return None

    if not x_api_key or x_api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide X-API-Key header.",
        )

    return x_api_key
