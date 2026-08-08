"""Tavsiya tizimiga rozilik bayrog'i.

Bu bayroq firmaning turlarini BOSHQA firmalarning mijozlariga ko'rsatadi,
shuning uchun ikki qoida muhim: sukut bo'yicha o'chiq bo'lsin va uni firma
o'zi yoqa olmasin.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company, CompanyStatus
from app.models.user import User, UserRole
from app.services.auth_service import _token_claims
from app.utils.security import create_access_token, hash_password
from tests.conftest import TestSessionLocal


def _sarlavha(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(_token_claims(user))}"}


async def _firma_id() -> int:
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        return firma.id


async def _superadmin_sarlavha() -> dict:
    async with TestSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.role == UserRole.SUPERADMIN))
        ).scalar_one()
        return _sarlavha(user)


async def _firma_admin_sarlavha() -> dict:
    async with TestSessionLocal() as db:
        user = (
            await db.execute(
                select(User).where(User.role == UserRole.ADMIN).limit(1)
            )
        ).scalar_one()
        return _sarlavha(user)


async def test_sukut_boyicha_ochiq(client: AsyncClient):
    """Yangi firma so'ralmasdan tavsiyaga tushmasligi kerak."""
    async with TestSessionLocal() as db:
        firma = Company(
            name="Yangi Firma",
            slug="yangi-firma",
            city="Buxoro",
            phone="998901234000",
            email="yangi@test.uz",
            status=CompanyStatus.APPROVED,
            tariff="boshlangich",
        )
        db.add(firma)
        await db.commit()
        assert firma.recommender_enabled is False


async def test_superadmin_yoqa_oladi(client: AsyncClient):
    firma_id = await _firma_id()
    javob = await client.patch(
        f"/api/superadmin/companies/{firma_id}/recommender?enabled=true",
        headers=await _superadmin_sarlavha(),
    )
    assert javob.status_code == 200, javob.text
    assert javob.json()["recommender_enabled"] is True

    async with TestSessionLocal() as db:
        firma = await db.get(Company, firma_id)
        assert firma.recommender_enabled is True


async def test_superadmin_ochira_oladi(client: AsyncClient):
    firma_id = await _firma_id()
    sarlavha = await _superadmin_sarlavha()
    await client.patch(
        f"/api/superadmin/companies/{firma_id}/recommender?enabled=true",
        headers=sarlavha,
    )
    javob = await client.patch(
        f"/api/superadmin/companies/{firma_id}/recommender?enabled=false",
        headers=sarlavha,
    )
    assert javob.json()["recommender_enabled"] is False


async def test_firma_admini_ozini_yoqa_olmaydi(client: AsyncClient):
    """ENG MUHIMI: qaror platforma darajasida qabul qilinadi.

    Aks holda har bir firma o'zini tavsiya ro'yxatiga qo'shib olardi va
    bayroqning ma'nosi qolmasdi.
    """
    firma_id = await _firma_id()
    javob = await client.patch(
        f"/api/superadmin/companies/{firma_id}/recommender?enabled=true",
        headers=await _firma_admin_sarlavha(),
    )
    assert javob.status_code == 403

    async with TestSessionLocal() as db:
        firma = await db.get(Company, firma_id)
        assert firma.recommender_enabled is False, "o'zgarmasligi kerak"


async def test_mavjud_bolmagan_firma_404(client: AsyncClient):
    javob = await client.patch(
        "/api/superadmin/companies/999999/recommender?enabled=true",
        headers=await _superadmin_sarlavha(),
    )
    assert javob.status_code == 404
