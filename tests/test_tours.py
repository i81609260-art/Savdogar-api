"""Tour endpoint tests."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient, email: str, password: str) -> str:
    """Helper to get access token."""
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_list_tours_empty(client: AsyncClient):
    """Empty tour list returns paginated response."""
    response = await client.get("/api/tours")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
