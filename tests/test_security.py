"""Xavfsizlik regressiya testlari.

Har bir test — bir marta topilgan va yopilgan aniq teshik. Test qizil bo'lsa,
o'sha teshik qaytib ochilgan degani.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.utils.security import decode_token, hash_password, verify_password

from tests.conftest import (
    COMPANY_ADMIN_EMAIL,
    COMPANY_ADMIN_PASSWORD,
    COMPANY_ADMIN_PHONE,
    TestSessionLocal,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


async def _make_tour(db_session, title="Test tur", city="Samarqand", slots=10):
    company = (await db_session.execute(select(Company))).scalars().first()
    tour = Tour(
        company_id=company.id,
        title=title,
        description="Tavsif",
        city=city,
        price=1_000_000,
        duration_days=3,
        available_slots=slots,
        is_active=True,
    )
    db_session.add(tour)
    await db_session.commit()
    return tour.id


# ── Tarif o'zlashtirish ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_registrationda_cheksiz_tarif_olib_bolmaydi(client: AsyncClient, db_session):
    """`tariff: cheksiz` yuborilsa ham firma eng quyi rejadan boshlanishi kerak.

    "cheksiz" reja sotilmaydi va to'lovdan ozod — uni o'zlashtirgan odam
    umrbod tekin, cheksiz obunaga ega bo'lardi.
    """
    response = await client.post("/api/auth/register", json={
        "company_name": "Hujum Firma",
        "company_city": "Toshkent",
        "company_phone": "998901112233",
        "company_email": "hujum@h.uz",
        "admin_email": "hujumchi@h.uz",
        "admin_password": "parol1234",
        "admin_full_name": "Hujumchi",
        "tariff": "cheksiz",
    })
    assert response.status_code == 200, response.text

    company = (await db_session.execute(
        select(Company).where(Company.email == "hujum@h.uz")
    )).scalar_one()
    assert company.tariff == "boshlangich", f"tarif o'zlashtirildi: {company.tariff}"


# ── JWT tarkibi ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokenda_company_id_bor(client: AsyncClient):
    """Realtime xona tekshiruvlari shu maydonga tayanadi."""
    response = await client.post("/api/auth/login", json={
        "email": COMPANY_ADMIN_EMAIL, "password": COMPANY_ADMIN_PASSWORD,
    })
    assert response.status_code == 200, response.text
    data = response.json()

    for token in (data["access_token"], data["refresh_token"]):
        payload = decode_token(token)
        assert payload["company_id"] is not None
        assert "branch_id" in payload


# ── Fayl yuklash ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_authsiz_ishlamaydi(client: AsyncClient):
    """Ochiq yuklash = disk to'ldirish va tekin fayl hosting."""
    response = await client.post("/api/upload", files={"file": ("a.png", PNG, "image/png")})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_auth_bilan_ishlaydi(client: AsyncClient, auth_headers):
    response = await client.post(
        "/api/upload",
        files={"file": ("a.png", PNG, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("/uploads/")


@pytest.mark.asyncio
async def test_upload_soxta_rasm_rad_etiladi(client: AsyncClient, auth_headers):
    """Kengaytmasi .png, ichi HTML — magic-byte tekshiruvi to'sishi kerak."""
    evil = b"<html><script>alert(1)</script></html>"
    response = await client.post(
        "/api/upload",
        files={"file": ("evil.png", evil, "image/png")},
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text


# ── Mehmon bronlash ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mehmon_broni_hisob_ochmaydi(client: AsyncClient, db_session):
    """Bron lead sifatida qabul qilinadi, foydalanuvchi hisobi yaratilmaydi."""
    tour_id = await _make_tour(db_session)
    response = await client.post("/api/bookings/guest", json={
        "tour_id": tour_id, "full_name": "Mehmon",
        "phone": "+998901234599", "guests_count": 1,
    })
    assert response.status_code == 200, response.text

    guests = (await db_session.execute(
        select(User).where(User.email.like("guest%"))
    )).scalars().all()
    assert guests == [], f"mehmon hisobi ochildi: {[g.email for g in guests]}"


@pytest.mark.asyncio
async def test_mehmon_broni_mavjud_adminni_ozgartirmaydi(client: AsyncClient, db_session):
    """Adminning telefon raqami yozilsa ham uning yozuvi tegilmasin."""
    tour_id = await _make_tour(db_session, "T2", "Buxoro", 5)
    response = await client.post("/api/bookings/guest", json={
        "tour_id": tour_id, "full_name": "HUJUMCHI NOMI",
        "phone": COMPANY_ADMIN_PHONE, "guests_count": 1,
    })
    assert response.status_code == 200, response.text

    admin = (await db_session.execute(
        select(User).where(User.email == COMPANY_ADMIN_EMAIL)
    )).scalar_one()
    assert admin.full_name == "Admin", "admin ismi o'zgartirildi!"
    assert admin.is_active is True, "admin faolsizlantirildi!"


def test_guest_bookings_moduli_xavfsiz():
    """Hozir soya qilingan modul jonlansa ham parol taxmin qilinmasin."""
    import inspect

    from app.routers import guest_bookings

    source = inspect.getsource(guest_bookings)
    assert "Guest_{clean_phone}" not in source, "parol telefondan hisoblanmoqda"
    assert "secrets.token_urlsafe" in source, "tasodifiy parol ishlatilmagan"
    assert "is_active=False" in source, "mehmon hisobi faol qolgan"


# ── Qo'ng'iroq yozuvlari ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_audio_authsiz_berilmaydi(client: AsyncClient):
    response = await client.get("/api/calls/audio/anything.mp3")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_call_audio_begona_firmaga_berilmaydi(client: AsyncClient, db_session):
    """Boshqa firma admini yozuvni so'rasa 404 olishi kerak."""
    from app.models.call_recording import CallRecording

    company = (await db_session.execute(select(Company))).scalars().first()
    db_session.add(CallRecording(
        company_id=company.id, user_id=1,
        file_url="/api/calls/audio/secret.mp3", status="tayyor",
    ))

    other = Company(
        name="Begona", slug="begona", city="Xiva", phone="998911111111",
        email="begona@b.uz", status=CompanyStatus.APPROVED, tariff="boshlangich",
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(User(
        email="begona-admin@b.uz", hashed_password=hash_password("parol123"),
        full_name="Begona Admin", role=UserRole.ADMIN,
        company_id=other.id, is_active=True,
    ))
    await db_session.commit()

    login = await client.post("/api/auth/login", json={
        "email": "begona-admin@b.uz", "password": "parol123",
    })
    assert login.status_code == 200, login.text

    response = await client.get(
        "/api/calls/audio/secret.mp3",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 404, "begona firma yozuvni ko'rdi!"


def test_call_yozuvlari_ochiq_papkada_saqlanmaydi():
    """file_url `/uploads/...` bo'lsa yozuv autentifikatsiyasiz tarqaladi."""
    import inspect

    from app.routers import calls

    source = inspect.getsource(calls)
    assert '"/uploads/calls/' not in source, "yozuv ochiq papkaga yozilmoqda"
    assert calls.AUDIO_URL_PREFIX == "/api/calls/audio/"
    assert "private" in calls._audio_dir()


# ── Telegram webhook ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_webhook_imzosiz_rad_etiladi(client: AsyncClient, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", "123:FAKE", raising=False)
    response = await client.post(
        "/api/telegram/webhook", json={"message": {"text": "/start"}}
    )
    assert response.json().get("ok") is False


def test_webhook_manzilida_bot_tokeni_yoq():
    """Token URL'ga yozilsa server loglariga tushib, bot egallanardi."""
    import inspect

    from app.routers import company_bot

    source = inspect.getsource(company_bot)
    assert "company-webhook/{token}" not in source
    assert "webhook_id_for(token)" in source
    assert "secret_token" in source


# ── CORS va sarlavhalar ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_xavfsizlik_sarlavhalari(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "referrer-policy" in response.headers


def test_cors_hammaga_ochiq_emas():
    import inspect

    from app import main

    source = inspect.getsource(main)
    assert 'allow_origins=["*"]' not in source
    assert "settings.cors_origin_list" in source


def test_socket_xonasi_firma_boyicha_tekshiriladi():
    import inspect

    from app import main

    source = inspect.getsource(main.join_room)
    assert 'f"company_{own}"' in source, "firma xonasi tekshiruvi yo'q"


# ── Superadmin ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_superadmin_paroli_startupda_tiklanmaydi(monkeypatch):
    """Parol almashtirilgach, seed_superadmin uni qayta yozmasligi kerak."""
    import app.database as dbmod
    from app.main import seed_superadmin

    async with TestSessionLocal() as session:
        admin = (await session.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )).scalar_one()
        admin.hashed_password = hash_password("YangiKuchliParol!42")
        session.add(admin)
        await session.commit()

    monkeypatch.setattr(dbmod, "AsyncSessionLocal", TestSessionLocal)
    await seed_superadmin()

    async with TestSessionLocal() as session:
        admin = (await session.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )).scalar_one()
        assert verify_password("YangiKuchliParol!42", admin.hashed_password), \
            "parol startup'da eskisiga qaytarildi!"


@pytest.mark.asyncio
async def test_superadmin_yoq_bolsa_yaratiladi(monkeypatch):
    """Yangi o'rnatishda sozlamalardagi login/parol ishlashi kerak."""
    import app.database as dbmod
    from app.main import seed_superadmin

    settings = get_settings()
    async with TestSessionLocal() as session:
        admin = (await session.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )).scalar_one()
        await session.delete(admin)
        await session.commit()

    monkeypatch.setattr(dbmod, "AsyncSessionLocal", TestSessionLocal)
    await seed_superadmin()

    async with TestSessionLocal() as session:
        admin = (await session.execute(
            select(User).where(User.role == UserRole.SUPERADMIN)
        )).scalar_one()
        assert admin.email == settings.superadmin_email
        assert verify_password(settings.superadmin_password, admin.hashed_password)
