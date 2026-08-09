"""Jo'nash shahri — "qayerdan qayerga" ko'rsatish uchun.

Ilgari turda faqat BORISH joyi bor edi (`city` + `country`), shuning uchun
mijoz turni ko'rganda qayerdan jo'nashini bilmasdi.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company
from app.models.tour import Tour
from tests.conftest import TestSessionLocal


async def _tur(departure: str | None) -> int:
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        tur = Tour(
            company_id=firma.id,
            title="Antalya dam olish",
            description="Dengiz bo'yida 7 kecha",
            city="Antalya",
            country="Turkiya",
            departure_city=departure,
            price=12_000_000,
            duration_days=7,
            available_slots=10,
        )
        db.add(tur)
        await db.commit()
        return tur.id


async def test_korsatilgan_shahar_qaytadi(client: AsyncClient):
    tid = await _tur("Samarqand")
    body = (await client.get(f"/api/tours/{tid}")).json()
    assert body["departure_city"] == "Samarqand"
    assert body["city"] == "Antalya"


async def test_bosh_bolsa_firma_shahri_olinadi(client: AsyncClient):
    """Turlarning aksariyati agentlik shahridan jo'naydi.

    Uni har turda qayta yozdirish ortiqcha, shuning uchun sukut qiymat bor.
    """
    tid = await _tur(None)
    body = (await client.get(f"/api/tours/{tid}")).json()
    # conftest'dagi sinov firmasi Toshkentda.
    assert body["departure_city"] == "Toshkent"


async def test_royxatda_ham_qaytadi(client: AsyncClient):
    """Karta ro'yxatda ham "qayerdan qayerga" ni ko'rsatishi kerak."""
    await _tur(None)
    items = (await client.get("/api/tours")).json()["items"]
    assert items[0]["departure_city"] == "Toshkent"


async def test_yaratishda_uzatiladi(client: AsyncClient, auth_headers):
    r = await client.post(
        "/api/tours",
        headers=auth_headers,
        json={
            "title": "Dubay sayohati",
            "description": "Shahar turi, 5 kecha",
            "city": "Dubay",
            "country": "BAA",
            "departure_city": "Buxoro",
            "price": 9_000_000,
            "duration_days": 5,
            "available_slots": 8,
        },
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["departure_city"] == "Buxoro"


async def test_tahrirlashda_ozgaradi(client: AsyncClient, auth_headers):
    tid = await _tur("Toshkent")
    r = await client.patch(
        f"/api/tours/{tid}",
        headers=auth_headers,
        json={"departure_city": "Namangan"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["departure_city"] == "Namangan"
