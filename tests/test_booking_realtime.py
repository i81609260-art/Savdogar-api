"""Bron holati o'zgarganda real-time xabar KIMGA borishi.

Ilgari `booking_updated` faqat `company_{id}` xonasiga yuborilardi. Ya'ni
admin tasdiqlaganda agentlik paneli darrov yangilanar, MIJOZ esa sahifani
qo'lda yangilamaguncha hamon "kutilmoqda" ni ko'rib turardi.
"""

from sqlalchemy import select

from app.models.booking import Booking, BookingStatus
from app.models.company import Company
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.booking import BookingStatusUpdate
from app.services.booking_service import BookingService
from app.utils.security import hash_password
from tests.conftest import COMPANY_ADMIN_EMAIL, TestSessionLocal


class _SoxtaSio:
    """Yuborilgan hodisalarni yig'ib turadi."""

    def __init__(self) -> None:
        self.yuborilgan: list[tuple[str, dict, str]] = []

    async def emit(self, event, data=None, room=None, **kwargs):  # noqa: D102
        self.yuborilgan.append((event, data, room))

    def xonalar(self, event: str) -> set[str]:
        return {r for e, _, r in self.yuborilgan if e == event}


async def _bron_yarat() -> tuple[int, int, int]:
    """Bron yaratadi. Qaytadi: (booking_id, user_id, company_id)."""
    async with TestSessionLocal() as db:
        firma = (
            await db.execute(select(Company).where(Company.slug == "test-firma"))
        ).scalar_one()

        mijoz = User(
            email="realtime@test.uz",
            hashed_password=hash_password("parol123"),
            full_name="Mijoz",
            role=UserRole.USER,
            is_active=True,
        )
        db.add(mijoz)

        tur = Tour(
            company_id=firma.id,
            title="Dubay 5 kecha",
            description="Shahar sayohati",
            city="Dubay",
            price=7_000_000,
            duration_days=5,
            available_slots=10,
        )
        db.add(tur)
        await db.flush()

        bron = Booking(
            user_id=mijoz.id,
            tour_id=tur.id,
            company_id=firma.id,
            status=BookingStatus.PENDING,
            guests_count=1,
            total_price=7_000_000,
        )
        db.add(bron)
        await db.commit()
        return bron.id, mijoz.id, firma.id


async def test_tasdiqlash_ikkala_tomonga_ham_boradi(client):
    """`client` fixture bazani tayyorlaydi; endpoint chaqirilmaydi."""
    booking_id, user_id, company_id = await _bron_yarat()
    sio = _SoxtaSio()

    async with TestSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.email == COMPANY_ADMIN_EMAIL))
        ).scalar_one()
        service = BookingService(db, sio)
        await service.update_status(
            admin, booking_id, BookingStatusUpdate(status=BookingStatus.CONFIRMED)
        )
        await db.commit()

    xonalar = sio.xonalar("booking_updated")
    assert f"company_{company_id}" in xonalar, "agentlik paneli"
    assert f"user_{user_id}" in xonalar, "MIJOZ — ilgari shu tushib qolgan edi"


async def test_bekor_qilish_ham_mijozga_boradi(client):
    booking_id, user_id, _ = await _bron_yarat()
    sio = _SoxtaSio()

    async with TestSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.email == COMPANY_ADMIN_EMAIL))
        ).scalar_one()
        await BookingService(db, sio).update_status(
            admin, booking_id, BookingStatusUpdate(status=BookingStatus.CANCELLED)
        )
        await db.commit()

    assert f"user_{user_id}" in sio.xonalar("booking_updated")


async def test_holat_qiymati_yuboriladi(client):
    """Mijoz tomonida qaysi holatga o'tganini bilish kerak."""
    booking_id, user_id, _ = await _bron_yarat()
    sio = _SoxtaSio()

    async with TestSessionLocal() as db:
        admin = (
            await db.execute(select(User).where(User.email == COMPANY_ADMIN_EMAIL))
        ).scalar_one()
        await BookingService(db, sio).update_status(
            admin, booking_id, BookingStatusUpdate(status=BookingStatus.CONFIRMED)
        )
        await db.commit()

    mijozga = [
        data
        for event, data, room in sio.yuborilgan
        if event == "booking_updated" and room == f"user_{user_id}"
    ]
    assert mijozga and mijozga[0]["status"] == "confirmed"
    assert mijozga[0]["booking_id"] == booking_id
