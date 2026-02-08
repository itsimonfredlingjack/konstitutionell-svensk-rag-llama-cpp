"""
Tests for Request ID middleware
"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_request_id_generated():
    """Test that request ID is auto-generated if not provided"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/constitutional/health")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_request_id_preserved():
    """Test that provided request ID is preserved"""
    test_request_id = "test-request-123"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/constitutional/health", headers={"X-Request-ID": test_request_id}
        )

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == test_request_id
