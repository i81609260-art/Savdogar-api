"""Brauzer kengaytmasi: kalitlar va narx qabul qilish.

Kalit UZOQ MUDDATLI va turagentning narx bazasiga yozish huquqini beradi.
Shuning uchun eng muhim tekshiruvlar shu yerda: kalit ochiq saqlanmasin,
begona firma kaliti bilan yozib bo'lmasin, bekor qilingani ishlamasin.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.company import Company, CompanyStatus
from app.models.extension_key import ExtensionKey
from app.models.tour_offer import TourOffer
from app.models.user import User, UserRole
from app.services.auth_service import _token_claims
from app.utils.security import create_access_token, hash_password
from tests.conftest import COMPANY_ADMIN_EMAIL, TestSessionLocal

PRICE_TEXT = (
    "ANTALYA 7 kecha\n"
    "Rixos Downtown 5* UAI — $850\n"
    "Delphin Imperial 5* AI — $720\n"
)


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(_token_claims(user))}"}


async def _admin_headers() -> dict:
    async with TestSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == COMPANY_ADMIN_EMAIL))
        ).scalar_one()
        return _headers(user)


async def _second_company_headers() -> dict:
    """Ikkinchi firma admini — begona kalit sinovlari uchun."""
    async with TestSessionLocal() as db:
        firma = Company(
            name="Ikkinchi", slug="ikkinchi", city="Samarqand",
            phone="998901112233", email="ikki@test.uz",
            status=CompanyStatus.APPROVED, tariff="boshlangich",
        )
        db.add(firma)
        await db.flush()
        user = User(
            email="admin@ikki.uz", hashed_password=hash_password("parol123"),
            full_name="Ikkinchi Admin", role=UserRole.ADMIN,
            company_id=firma.id, is_active=True,
        )
        db.add(user)
        await db.commit()
        return _headers(user)


async def _make_key(client: AsyncClient, headers: dict) -> str:
    r = await client.post("/api/extension/keys", headers=headers, json={"label": "Ish"})
    assert r.status_code == 201, r.text
    return r.json()["key"]


# --------------------------------------------------------------------------
# Kalit yaratish va saqlash
# --------------------------------------------------------------------------
async def test_kalit_yaratiladi_va_bir_marta_korsatiladi(client: AsyncClient):
    h = await _admin_headers()
    created = (await client.post("/api/extension/keys", headers=h, json={})).json()
    assert created["key"].startswith("trf_")

    # Ro'yxatda ochiq kalit BO'LMASLIGI kerak — faqat prefiks.
    rows = (await client.get("/api/extension/keys", headers=h)).json()
    assert "key" not in rows[0]
    assert rows[0]["key_prefix"] == created["key"][:12]


async def test_kalit_bazada_ochiq_saqlanmaydi(client: AsyncClient):
    """ENG MUHIMI: baza sizib chiqsa ham kalitlar ishlatib bo'lmasin."""
    h = await _admin_headers()
    raw = await _make_key(client, h)

    async with TestSessionLocal() as db:
        key = (await db.execute(select(ExtensionKey))).scalars().first()
        assert key.key_hash != raw
        assert raw not in key.key_hash


async def test_oddiy_foydalanuvchi_kalit_yarata_olmaydi(client: AsyncClient):
    async with TestSessionLocal() as db:
        mijoz = User(
            email="mijoz@ext.uz", hashed_password=hash_password("parol123"),
            full_name="Mijoz", role=UserRole.USER, is_active=True,
        )
        db.add(mijoz)
        await db.commit()
        h = _headers(mijoz)

    r = await client.post("/api/extension/keys", headers=h, json={})
    assert r.status_code == 403


# --------------------------------------------------------------------------
# Narx qabul qilish
# --------------------------------------------------------------------------
async def test_kengaytma_narx_yuboradi(client: AsyncClient):
    h = await _admin_headers()
    raw = await _make_key(client, h)

    r = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT, "url": "https://b2b.operator.uz/search"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 2


async def test_narx_ozining_firmasiga_yoziladi(client: AsyncClient):
    """Kalit qaysi firmaniki bo'lsa, narx o'shanikiga tushishi kerak."""
    h = await _admin_headers()
    raw = await _make_key(client, h)
    await client.post(
        "/api/extension/pricelist", headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT},
    )

    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        offers = (await db.execute(select(TourOffer))).scalars().all()
        assert offers and all(o.company_id == firma.id for o in offers)


async def test_manba_extension_deb_belgilanadi(client: AsyncClient):
    """Manba ko'rinib tursin — agent narx qayerdan kelganini bilishi kerak."""
    h = await _admin_headers()
    raw = await _make_key(client, h)
    await client.post(
        "/api/extension/pricelist", headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT},
    )
    async with TestSessionLocal() as db:
        offer = (await db.execute(select(TourOffer))).scalars().first()
        assert offer.source == "extension"


# --------------------------------------------------------------------------
# Xavfsizlik
# --------------------------------------------------------------------------
async def test_kalitsiz_rad_etiladi(client: AsyncClient):
    r = await client.post("/api/extension/pricelist", json={"text": PRICE_TEXT})
    assert r.status_code == 401


async def test_notogri_kalit_rad_etiladi(client: AsyncClient):
    r = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": "trf_soxta_kalit_1234567890"},
        json={"text": PRICE_TEXT},
    )
    assert r.status_code == 401


async def test_bekor_qilingan_kalit_ishlamaydi(client: AsyncClient):
    h = await _admin_headers()
    created = (await client.post("/api/extension/keys", headers=h, json={})).json()

    await client.delete(f"/api/extension/keys/{created['id']}", headers=h)

    r = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": created["key"]},
        json={"text": PRICE_TEXT},
    )
    assert r.status_code == 401


async def test_begona_firma_kalitni_bekor_qila_olmaydi(client: AsyncClient):
    """Boshqa firmaning admini ham kalitga tegmasligi kerak."""
    h = await _admin_headers()
    created = (await client.post("/api/extension/keys", headers=h, json={})).json()

    begona = await _second_company_headers()
    r = await client.delete(f"/api/extension/keys/{created['id']}", headers=begona)
    assert r.status_code == 404

    # Kalit hali ishlashi kerak.
    ok = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": created["key"]},
        json={"text": PRICE_TEXT},
    )
    assert ok.status_code == 200


async def test_begona_firma_kalitni_kora_olmaydi(client: AsyncClient):
    h = await _admin_headers()
    await _make_key(client, h)

    begona = await _second_company_headers()
    rows = (await client.get("/api/extension/keys", headers=begona)).json()
    assert rows == []


async def test_juda_uzun_matn_rad_etiladi(client: AsyncClient):
    h = await _admin_headers()
    raw = await _make_key(client, h)
    r = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": raw},
        json={"text": "a" * 200_001},
    )
    assert r.status_code == 422


# ── Ko'rib chiqish (dry_run) ─────────────────────────────────────────


async def test_korib_chiqish_saqlamaydi(client: AsyncClient):
    """Agent nima yuborayotganini ko'rmasdan bosmasin.

    Bir bosqichli bo'lganda xato sahifadan olingan o'nlab qator jimgina
    bazaga tushardi va uni qo'lda tozalash kerak bo'lardi.
    """
    h = await _admin_headers()
    raw = await _make_key(client, h)

    r = await client.post(
        "/api/extension/pricelist",
        headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT, "dry_run": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["saved"] == 0
    assert body["found"] == 2
    assert len(body["preview"]) == 2

    async with TestSessionLocal() as db:
        offers = (await db.execute(select(TourOffer))).scalars().all()
    assert offers == [], "ko'rib chiqishda hech nima saqlanmasligi kerak"


async def test_korib_chiqishdan_keyin_yuborish_ishlaydi(client: AsyncClient):
    h = await _admin_headers()
    raw = await _make_key(client, h)

    await client.post(
        "/api/extension/pricelist", headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT, "dry_run": True},
    )
    r = await client.post(
        "/api/extension/pricelist", headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT},
    )
    assert r.json()["saved"] == 2
    assert r.json()["dry_run"] is False


async def test_korish_qatori_bosh_maydonlarni_yozmaydi(client: AsyncClient):
    """"None · None" ko'rgan agent tahlil ishlamadi deb o'ylardi."""
    h = await _admin_headers()
    raw = await _make_key(client, h)

    body = (await client.post(
        "/api/extension/pricelist", headers={"X-API-Key": raw},
        json={"text": PRICE_TEXT, "dry_run": True},
    )).json()

    for line in body["preview"]:
        assert line.strip(), "bo'sh qator"
        assert "None" not in line
        assert not line.startswith("·")
        assert not line.endswith("·")


async def test_kalitsiz_korib_chiqib_ham_bolmaydi(client: AsyncClient):
    """`dry_run` saqlamasa ham tahlilchini ochiq qoldirmaydi."""
    r = await client.post(
        "/api/extension/pricelist", json={"text": PRICE_TEXT, "dry_run": True}
    )
    assert r.status_code == 401
