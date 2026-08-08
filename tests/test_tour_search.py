"""Turlarni qidirish: saralash va yo'nalishlar ro'yxati.

Ikkalasi ham qidiruv oqimini yaxshilash uchun qo'shildi: mijoz katalogni
"yangi qo'shilgani" tartibida emas, ARZONIDAN ko'radi; yo'nalish esa qo'lda
terilmasdan ro'yxatdan tanlanadi.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company
from app.models.tour import Tour
from tests.conftest import TestSessionLocal


async def _turlar_yarat() -> None:
    """Uch xil narx va shaharda tur yaratadi."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()

        db.add_all([
            Tour(
                company_id=firma.id,
                title="Antalya arzon",
                description="Dengiz bo'yida",
                city="Antalya",
                price=3_000_000,
                duration_days=5,
                available_slots=10,
            ),
            Tour(
                company_id=firma.id,
                title="Antalya qimmat",
                description="Lyuks mehmonxona",
                city="Antalya",
                price=15_000_000,
                duration_days=7,
                available_slots=5,
            ),
            Tour(
                company_id=firma.id,
                title="Dubay sayohati",
                description="Shahar turi",
                city="Dubay",
                price=9_000_000,
                duration_days=4,
                available_slots=8,
            ),
        ])
        await db.commit()


# --------------------------------------------------------------------------
# Saralash
# --------------------------------------------------------------------------
async def test_arzonidan_saralash(client: AsyncClient):
    await _turlar_yarat()
    narxlar = [
        t["price"]
        for t in (await client.get("/api/tours?sort=narx_arzon")).json()["items"]
    ]
    assert narxlar == sorted(narxlar), narxlar


async def test_qimmatidan_saralash(client: AsyncClient):
    await _turlar_yarat()
    narxlar = [
        t["price"]
        for t in (await client.get("/api/tours?sort=narx_qimmat")).json()["items"]
    ]
    assert narxlar == sorted(narxlar, reverse=True), narxlar


async def test_notogri_saralash_yiqilmaydi(client: AsyncClient):
    """Noma'lum qiymat sukutga tushadi, 422 EMAS.

    Qidiruv manzili foydalanuvchi ulashadigan havola bo'lishi mumkin —
    eskirgan `sort` qiymati butun sahifani yiqitmasligi kerak.
    """
    await _turlar_yarat()
    javob = await client.get("/api/tours?sort=allaqanday_axlat")
    assert javob.status_code == 200
    assert len(javob.json()["items"]) == 3


async def test_saralash_filtr_bilan_birga(client: AsyncClient):
    """Saralash filtrni buzmasligi kerak."""
    await _turlar_yarat()
    items = (
        await client.get("/api/tours?city=Antalya&sort=narx_arzon")
    ).json()["items"]
    assert [t["city"] for t in items] == ["Antalya", "Antalya"]
    assert items[0]["price"] < items[1]["price"]


# --------------------------------------------------------------------------
# Yo'nalishlar ro'yxati
# --------------------------------------------------------------------------
async def test_shaharlar_soni_bilan_qaytadi(client: AsyncClient):
    await _turlar_yarat()
    rows = (await client.get("/api/tours/cities")).json()
    xarita = {r["city"]: r["count"] for r in rows}
    assert xarita == {"Antalya": 2, "Dubay": 1}


async def test_shaharlar_kopidan_kamiga(client: AsyncClient):
    """Ommabop yo'nalish yuqorida tursin — taklif ro'yxati shunday foydali."""
    await _turlar_yarat()
    rows = (await client.get("/api/tours/cities")).json()
    assert [r["city"] for r in rows][0] == "Antalya"


async def test_faol_bolmagan_tur_shaharlarga_tushmaydi(client: AsyncClient):
    """O'chirilgan turning shahri taklif qilinmasin — u bo'sh natija berardi."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        db.add(Tour(
            company_id=firma.id,
            title="Yashirin",
            description="Faol emas",
            city="Samarqand",
            price=1_000_000,
            duration_days=2,
            available_slots=5,
            is_active=False,
        ))
        await db.commit()

    rows = (await client.get("/api/tours/cities")).json()
    assert "Samarqand" not in [r["city"] for r in rows]


async def test_cities_tur_raqami_deb_oqilmaydi(client: AsyncClient):
    """`/cities` marshruti `/{tour_id}` dan oldin turishi kerak.

    Tartib buzilsa "cities" tur raqami deb o'qilib 422 qaytarardi.
    """
    javob = await client.get("/api/tours/cities")
    assert javob.status_code == 200
    assert isinstance(javob.json(), list)


# --------------------------------------------------------------------------
# Valyutalararo saralash
# --------------------------------------------------------------------------
async def test_saralash_valyutalarni_aralashtirmaydi(client: AsyncClient):
    """ENG MUHIMI: 10 001 EUR 12 mln so'mdan QIMMAT.

    Xom `price` bo'yicha saralaganda 10001 < 12000000 bo'lgani uchun
    yevroli tur "arzon" deb birinchi chiqardi. Endi solishtirish so'mda
    bo'ladi.
    """
    import app.services.currency as cur

    cur._cache.clear()
    cur._cache.update({"UZS": 1.0, "EUR": 13749.46})

    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        db.add_all([
            Tour(
                company_id=firma.id, title="Somdagi", description="d",
                city="Toshkent", price=12_000_000, currency="UZS",
                price_uzs=12_000_000, duration_days=3, available_slots=5,
            ),
            Tour(
                company_id=firma.id, title="Yevrodagi", description="d",
                city="Parij", price=10_001, currency="EUR",
                price_uzs=10_001 * 13749.46, duration_days=3, available_slots=5,
            ),
        ])
        await db.commit()

    items = (await client.get("/api/tours?sort=narx_arzon")).json()["items"]
    assert [t["title"] for t in items] == ["Somdagi", "Yevrodagi"], (
        "so'mdagi tur arzonroq bo'lishi kerak"
    )


async def test_narx_filtri_ham_somda(client: AsyncClient):
    """"5-15 mln" filtri 10 001 EUR turni ICHIGA OLMASLIGI kerak.

    Xom raqam bilan solishtirilganda 10001 oraliqqa tushib qolardi.
    """
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        db.add_all([
            Tour(
                company_id=firma.id, title="Somdagi", description="d",
                city="Toshkent", price=12_000_000, currency="UZS",
                price_uzs=12_000_000, duration_days=3, available_slots=5,
            ),
            Tour(
                company_id=firma.id, title="Yevrodagi", description="d",
                city="Parij", price=10_001, currency="EUR",
                price_uzs=10_001 * 13749.46, duration_days=3, available_slots=5,
            ),
        ])
        await db.commit()

    items = (
        await client.get("/api/tours?min_price=5000000&max_price=15000000")
    ).json()["items"]
    assert [t["title"] for t in items] == ["Somdagi"]
