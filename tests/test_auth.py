"""Authentication endpoint tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """Health endpoint returns ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_superadmin_login(client: AsyncClient):
    """Superadmin can login with credentials."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "superadmin"


@pytest.mark.asyncio
async def test_register_company(client: AsyncClient):
    """Company registration creates pending application."""
    response = await client.post(
        "/api/auth/register",
        json={
            "company_name": "Test Travel",
            "company_city": "Toshkent",
            "company_phone": "+998901234567",
            "company_email": "company@test.uz",
            "admin_email": "admin@test.uz",
            "admin_password": "AdminPass123!",
            "admin_full_name": "Test Admin",
        },
    )
    assert response.status_code == 200
    assert "company_id" in response.json()


@pytest.mark.asyncio
async def test_register_user_and_login(client: AsyncClient):
    """User can register and login."""
    await client.post(
        "/api/auth/register/user",
        json={
            "email": "user@test.uz",
            "password": "UserPass123!",
            "full_name": "Test User",
        },
    )
    response = await client.post(
        "/api/auth/login",
        json={"email": "user@test.uz", "password": "UserPass123!"},
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"
