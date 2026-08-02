"""Authentication endpoint tests."""

import pytest
from httpx import AsyncClient

from app.config import get_settings


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """Health endpoint returns ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_admin_login(client: AsyncClient):
    """Login formasiga "admin" yozilsa superadmin emailiga o'giriladi."""
    settings = get_settings()
    response = await client.post(
        "/api/auth/login",
        json={
            "email": settings.superadmin_login_alias,
            "password": settings.superadmin_password,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "superadmin"
    assert data["user"]["email"] == settings.superadmin_email


@pytest.mark.asyncio
async def test_register_company(client: AsyncClient, db_session):
    """Company registration creates pending application."""
    response = await client.post(
        "/api/auth/register",
        json={
            "company_name": "Test Travel",
            "company_city": "Toshkent",
            "company_phone": "+998901234567",
            "company_email": "company@test.uz",
            "admin_email": "yangi@test.uz",
            "admin_password": "AdminPass123!",
            "admin_full_name": "Test Admin",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    # AuthResponse: user + tokenlar. company_id user ichida keladi.
    assert data["user"]["company_id"] is not None
    assert data["user"]["role"] == "admin"

    # Firma superadmin tasdig'ini kutib turishi kerak.
    from sqlalchemy import select

    from app.models.company import Company, CompanyStatus

    company = (await db_session.execute(
        select(Company).where(Company.email == "company@test.uz")
    )).scalar_one()
    assert company.status == CompanyStatus.PENDING
    # Tarif mijoz tanlaganidan emas, har doim eng quyi rejadan boshlanadi.
    assert company.tariff == "boshlangich"


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
