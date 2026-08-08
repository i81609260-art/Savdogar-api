"""Bron yozishuvi — ruxsat qoidasi va suhbat oqimi.

Eng muhim tekshiruv: suhbatni FAQAT o'sha bronning ikki tomoni ko'radi.
Bu joyda xato bo'lsa, mijozning agentlik bilan shaxsiy yozishuvi begona
odamga ochilib qoladi.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.booking import Booking, BookingStatus
from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.auth_service import _token_claims
from app.utils.security import create_access_token, hash_password
from tests.conftest import COMPANY_ADMIN_EMAIL, TestSessionLocal


def _sarlavha(user: User) -> dict:
    """Token to'g'ridan-to'g'ri yasaladi — login endpointi rate-limit qiladi."""
    return {"Authorization": f"Bearer {create_access_token(_token_claims(user))}"}


async def _muhit() -> dict:
    """Bron, uning ikki tomoni va ikki begona odam.

    Qaytadi: `booking_id` va to'rt xil sarlavha — mijoz, agentlik admini,
    begona mijoz, begona agentlik admini.
    """
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()
        agentlik_admin = (
            await db.execute(select(User).where(User.email == COMPANY_ADMIN_EMAIL))
        ).scalar_one()

        mijoz = User(
            email="mijoz@test.uz",
            hashed_password=hash_password("parol123"),
            full_name="Mijoz",
            role=UserRole.USER,
            is_active=True,
        )
        begona_mijoz = User(
            email="begona@test.uz",
            hashed_password=hash_password("parol123"),
            full_name="Begona Mijoz",
            role=UserRole.USER,
            is_active=True,
        )
        db.add_all([mijoz, begona_mijoz])

        # Ikkinchi agentlik — uning admini ham suhbatni ko'rmasligi kerak.
        boshqa_firma = Company(
            name="Boshqa Agentlik",
            slug="boshqa-agentlik",
            city="Samarqand",
            phone="998901112233",
            email="boshqa@test.uz",
            status=CompanyStatus.APPROVED,
            tariff="boshlangich",
        )
        db.add(boshqa_firma)
        await db.flush()

        begona_admin = User(
            email="admin@boshqa.uz",
            hashed_password=hash_password("parol123"),
            full_name="Begona Admin",
            role=UserRole.ADMIN,
            company_id=boshqa_firma.id,
            is_active=True,
        )
        db.add(begona_admin)

        tur = Tour(
            company_id=firma.id,
            title="Antalya 7 kecha",
            description="Dengiz bo'yida dam olish",
            city="Antalya",
            price=5_000_000,
            duration_days=7,
            available_slots=10,
        )
        db.add(tur)
        await db.flush()

        bron = Booking(
            user_id=mijoz.id,
            tour_id=tur.id,
            company_id=firma.id,
            status=BookingStatus.PENDING,
            guests_count=2,
            total_price=10_000_000,
        )
        db.add(bron)
        await db.commit()

        return {
            "booking_id": bron.id,
            "mijoz": _sarlavha(mijoz),
            "agentlik": _sarlavha(agentlik_admin),
            "begona_mijoz": _sarlavha(begona_mijoz),
            "begona_admin": _sarlavha(begona_admin),
        }


# --------------------------------------------------------------------------
# Ruxsat — eng muhim qism
# --------------------------------------------------------------------------
async def test_ikki_tomon_ham_yoza_oladi(client: AsyncClient):
    m = await _muhit()
    bid = m["booking_id"]

    yuborildi = await client.post(
        f"/api/bookings/{bid}/messages",
        headers=m["mijoz"],
        json={"text": "Bolamga chegirma bormi?"},
    )
    assert yuborildi.status_code == 201, yuborildi.text
    assert yuborildi.json()["sender_role"] == "mijoz"

    javob = await client.post(
        f"/api/bookings/{bid}/messages",
        headers=m["agentlik"],
        json={"text": "Ha, 6 yoshgacha bepul."},
    )
    assert javob.status_code == 201, javob.text
    assert javob.json()["sender_role"] == "agentlik"


async def test_begona_mijoz_kora_olmaydi(client: AsyncClient):
    m = await _muhit()
    bid = m["booking_id"]
    await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "salom"}
    )

    korish = await client.get(f"/api/bookings/{bid}/messages", headers=m["begona_mijoz"])
    assert korish.status_code == 404

    yozish = await client.post(
        f"/api/bookings/{bid}/messages",
        headers=m["begona_mijoz"],
        json={"text": "men ham yozaman"},
    )
    assert yozish.status_code == 404


async def test_begona_agentlik_kora_olmaydi(client: AsyncClient):
    """Boshqa firmaning ADMINI ham ko'ra olmasligi kerak.

    Eng nozik holat: u haqiqiy admin, roli to'g'ri — faqat bron boshqa
    firmaniki. `company_id` tekshiruvi tushib qolsa aynan shu joy sizadi.
    """
    m = await _muhit()
    bid = m["booking_id"]
    await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "sir"}
    )

    korish = await client.get(f"/api/bookings/{bid}/messages", headers=m["begona_admin"])
    assert korish.status_code == 404
    assert "sir" not in korish.text


async def test_mavjud_bolmagan_bron_404(client: AsyncClient):
    """Yo'q bron ham, begona bron ham BIR XIL javob berishi kerak.

    Aks holda javob kodining o'zi ma'lumot berardi: 403 olgan odam
    "bunday bron bor, lekin meniki emas" degan xulosaga kelardi.
    """
    m = await _muhit()
    javob = await client.get("/api/bookings/999999/messages", headers=m["mijoz"])
    assert javob.status_code == 404


# --------------------------------------------------------------------------
# Suhbat oqimi
# --------------------------------------------------------------------------
async def test_xabarlar_eskisidan_yangisiga(client: AsyncClient):
    m = await _muhit()
    bid = m["booking_id"]
    for matn in ("birinchi", "ikkinchi", "uchinchi"):
        await client.post(
            f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": matn}
        )

    royxat = (
        await client.get(f"/api/bookings/{bid}/messages", headers=m["mijoz"])
    ).json()
    assert [x["text"] for x in royxat] == ["birinchi", "ikkinchi", "uchinchi"]


async def test_is_mine_tomonga_qarab_ozgaradi(client: AsyncClient):
    """Bir xil xabar ikki tomonda turlicha belgilanadi."""
    m = await _muhit()
    bid = m["booking_id"]
    await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "savol"}
    )

    mijoz_korgan = (
        await client.get(f"/api/bookings/{bid}/messages", headers=m["mijoz"])
    ).json()[0]
    agentlik_korgan = (
        await client.get(f"/api/bookings/{bid}/messages", headers=m["agentlik"])
    ).json()[0]

    assert mijoz_korgan["is_mine"] is True
    assert agentlik_korgan["is_mine"] is False


async def test_oqilgan_deb_belgilash_faqat_qarshi_tomonniki(client: AsyncClient):
    """O'z xabaringizni o'qilgan deb belgilash mantiqsiz."""
    m = await _muhit()
    bid = m["booking_id"]
    await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "savol"}
    )
    await client.post(
        f"/api/bookings/{bid}/messages", headers=m["agentlik"], json={"text": "javob"}
    )

    natija = (
        await client.post(f"/api/bookings/{bid}/messages/read", headers=m["mijoz"])
    ).json()
    assert natija["belgilandi"] == 1

    royxat = (
        await client.get(f"/api/bookings/{bid}/messages", headers=m["mijoz"])
    ).json()
    mijoznikilar = [x for x in royxat if x["sender_role"] == "mijoz"]
    agentliknikilar = [x for x in royxat if x["sender_role"] == "agentlik"]
    assert mijoznikilar[0]["read_at"] is None, "o'z xabari belgilanmasin"
    assert agentliknikilar[0]["read_at"] is not None


async def test_bosh_xabar_rad_etiladi(client: AsyncClient):
    m = await _muhit()
    bid = m["booking_id"]
    javob = await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "   "}
    )
    assert javob.status_code == 422


async def test_juda_uzun_xabar_rad_etiladi(client: AsyncClient):
    m = await _muhit()
    bid = m["booking_id"]
    javob = await client.post(
        f"/api/bookings/{bid}/messages", headers=m["mijoz"], json={"text": "a" * 2001}
    )
    assert javob.status_code == 422
