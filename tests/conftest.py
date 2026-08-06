"""Pytest fixtures for SAYR API tests."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.utils.limiter import limiter

# Testlarda tezlik chegarasi o'chirilgan. `/api/auth/login` daqiqasiga 10 ta
# so'rovga ruxsat beradi — testlar soni oshgani sari ular mahsulot xatosi
# tufayli emas, chegara tufayli yiqila boshlaydi va natija testlar tartibiga
# bog'liq bo'lib qoladi. Chegaraning o'zi production sozlamasi bo'lib
# qolaveradi.
limiter.enabled = False
from app.models.company import Company, CompanyStatus
from app.models.user import User, UserRole
from app.utils.security import hash_password

settings = get_settings()

# Firma admini uchun test hisobi — ko'p testlar shunga tayanadi.
COMPANY_ADMIN_EMAIL = "admin@test.uz"
COMPANY_ADMIN_PASSWORD = "parol123"
COMPANY_ADMIN_PHONE = "998900000001"

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_sayr.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Reset database before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        # Superadmin sozlamalardagi email/parol bilan yaratiladi — shunda
        # "admin" taxallusi orqali kirish ham haqiqiy holatdek tekshiriladi.
        session.add(User(
            email=settings.superadmin_email,
            hashed_password=hash_password(settings.superadmin_password),
            full_name="Super Admin",
            role=UserRole.SUPERADMIN,
            is_active=True,
        ))

        company = Company(
            name="Test Firma",
            slug="test-firma",
            city="Toshkent",
            phone="998901234567",
            email="firma@test.uz",
            status=CompanyStatus.APPROVED,
            tariff="boshlangich",
        )
        session.add(company)
        await session.flush()

        session.add(User(
            email=COMPANY_ADMIN_EMAIL,
            hashed_password=hash_password(COMPANY_ADMIN_PASSWORD),
            full_name="Admin",
            phone=COMPANY_ADMIN_PHONE,
            role=UserRole.ADMIN,
            company_id=company.id,
            is_active=True,
        ))
        await session.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override database dependency for tests."""
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client."""
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Test bazasiga to'g'ridan-to'g'ri sessiya (natijani tekshirish uchun)."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def admin_token(client: AsyncClient) -> str:
    """Firma admini uchun access token."""
    response = await client.post(
        "/api/auth/login",
        json={"email": COMPANY_ADMIN_EMAIL, "password": COMPANY_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
def auth_headers(admin_token: str) -> dict:
    """Authorization sarlavhasi."""
    return {"Authorization": f"Bearer {admin_token}"}
