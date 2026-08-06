"""Firma botining qo'shimcha buyruqlari: `/id`, `/malumot`, `/hisobot`.

Uchtasining ruxsat darajasi har xil va bu farq testlarning asosiy mavzusi:

  * `/id`      — hammaga (o'z ma'lumoti);
  * `/malumot` — hammaga (firmaning ommaviy ma'lumoti);
  * `/hisobot` — FAQAT xodimga (ichida daromad va mijozlar soni).

Hisobot mijozga chiqib ketsa bu ma'lumot sizishi — firma daromadini
begonaga ko'rsatish demakdir.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.company import Company, CompanyStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.telegram_commands import (
    build_id_reply,
    build_report_reply,
    build_site_reply,
    try_handle_command,
)
from app.utils.security import hash_password

STAFF_CHAT = "555000111"
CUSTOMER_CHAT = "999888777"
SITE_URL = "https://turify.xyz/sites/agentlik"


def _msg(chat_id, text=None, chat_type="private", sender=None) -> dict:
    message: dict = {"chat": {"id": chat_id, "type": chat_type}}
    if text is not None:
        message["text"] = text
    message["from"] = sender or {"id": chat_id, "first_name": "Test"}
    return message


async def _company(db: AsyncSession, **kw) -> Company:
    company = Company(
        name=kw.get("name", "Fayz Travel"), slug=kw.get("slug", "fayz"),
        city="Toshkent", phone="998901234567", email="info@fayz.uz",
        status=CompanyStatus.APPROVED, tariff="boshlangich",
        description=kw.get("description"), company_info=kw.get("company_info"),
    )
    db.add(company)
    await db.flush()
    return company


async def _staff(db: AsyncSession, company_id, chat_id=STAFF_CHAT,
                 role=UserRole.ADMIN, email="xodim@test.uz") -> User:
    user = User(
        email=email, hashed_password=hash_password("parol123"),
        full_name="Islom Xodimov", role=role, company_id=company_id,
        telegram_chat_id=chat_id, is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


# --------------------------------------------------------------------------
# /id
# --------------------------------------------------------------------------
def test_id_shows_user_id():
    reply = build_id_reply(_msg(111222333, "/id"))
    assert "111222333" in reply
    assert "User ID" in reply


def test_id_includes_username_and_name():
    reply = build_id_reply(
        _msg(111, "/id", sender={
            "id": 111, "username": "islom", "first_name": "Islom", "last_name": "M",
        })
    )
    assert "@islom" in reply
    assert "Islom M" in reply


def test_id_shows_chat_id_in_group():
    """Guruhda chat ID user ID dan farq qiladi — bildirishnoma guruhga
    kelishi kerak bo'lsa aynan shu kerak."""
    message = {
        "chat": {"id": -1001234567890, "type": "supergroup"},
        "from": {"id": 111, "first_name": "Islom"},
    }
    reply = build_id_reply(message)
    assert "-1001234567890" in reply
    assert "Chat ID" in reply


def test_id_hides_chat_id_in_private():
    """Shaxsiy chatda ular bir xil — ikki marta ko'rsatib chalkashtirmaymiz.

    "Chat ID" iborasi tushuntirish matnida ham uchraydi, shuning uchun
    aynan qiymat ko'rsatilgan QATOR tekshiriladi."""
    reply = build_id_reply(_msg(111, "/id"))
    assert "💬 Chat ID" not in reply


def test_id_explains_what_it_is_for():
    """Raqamning o'zi yetarli emas — u bilan nima qilishni ham aytish kerak."""
    reply = build_id_reply(_msg(111, "/id"))
    assert "Integratsiyalar" in reply
    assert "nusxalang" in reply.lower()


def test_id_explains_group_case():
    assert "guruh" in build_id_reply(_msg(111, "/id")).lower()


@pytest.mark.asyncio
async def test_id_command_open_to_everyone(db_session: AsyncSession):
    """`/id` — foydalanuvchining O'Z ma'lumoti, bog'lanish shart emas."""
    company = await _company(db_session)
    reply = await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT, "/id"), SITE_URL
    )
    assert reply is not None and "User ID" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_id_button_text_works(db_session: AsyncSession):
    """Klaviaturadagi tugma matni ham ishlasin."""
    company = await _company(db_session)
    reply = await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT, "🆔 ID"), SITE_URL
    )
    assert reply is not None and "User ID" in reply
    await db_session.rollback()


# --------------------------------------------------------------------------
# Sayt ma'lumoti
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_site_reply_contains_contacts(db_session: AsyncSession):
    company = await _company(db_session, description="Eng yaxshi turlar")
    reply = await build_site_reply(db_session, company, SITE_URL)
    assert "Fayz Travel" in reply
    assert "Eng yaxshi turlar" in reply
    assert "998901234567" in reply
    assert "info@fayz.uz" in reply
    assert SITE_URL in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_site_reply_includes_company_info(db_session: AsyncSession):
    """Admin panelda to'ldirilgan erkin matn ham chiqsin."""
    company = await _company(
        db_session, company_info="2010 yildan beri ishlaymiz. Litsenziya №123."
    )
    reply = await build_site_reply(db_session, company, SITE_URL)
    assert "Litsenziya" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_site_reply_counts_active_tours(db_session: AsyncSession):
    company = await _company(db_session)
    for i in range(3):
        db_session.add(Tour(
            company_id=company.id, title=f"Tur {i}", description="x", city="Antalya",
            price=1000, available_slots=10, is_active=True,
        ))
    await db_session.flush()

    reply = await build_site_reply(db_session, company, SITE_URL)
    assert "Faol turlar" in reply and "3" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_site_reply_fits_telegram_limit(db_session: AsyncSession):
    """Telegram xabari 4096 belgidan oshmasin — aks holda umuman yetib
    bormaydi."""
    company = await _company(
        db_session, description="x" * 5000, company_info="y" * 5000
    )
    reply = await build_site_reply(db_session, company, SITE_URL)
    assert len(reply) <= 4096
    await db_session.rollback()


@pytest.mark.asyncio
async def test_info_command(db_session: AsyncSession):
    company = await _company(db_session)
    reply = await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT, "/malumot"), SITE_URL
    )
    assert reply is not None and "Fayz Travel" in reply
    await db_session.rollback()


# --------------------------------------------------------------------------
# /hisobot — ruxsat
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_hidden_from_customer(db_session: AsyncSession):
    """Mijoz firmaning daromadini KO'RMASLIGI kerak."""
    company = await _company(db_session)
    await _staff(db_session, company.id)

    assert await build_report_reply(db_session, company.id, CUSTOMER_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_command_tells_customer_to_link(db_session: AsyncSession):
    """Mijozga hisobot borligi ham oshkor qilinmasin — faqat yo'riqnoma."""
    company = await _company(db_session)
    reply = await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT, "/hisobot"), SITE_URL
    )
    assert reply is not None
    assert "/link" in reply
    assert "daromad" not in reply.lower()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_hidden_from_other_company_staff(db_session: AsyncSession):
    """Boshqa firma xodimi shu firmaning hisobotini ko'rmasin."""
    a = await _company(db_session, slug="agent-a", name="A")
    b = await _company(db_session, slug="agent-b", name="B")
    await _staff(db_session, b.id)

    assert await build_report_reply(db_session, a.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_visible_to_own_staff(db_session: AsyncSession):
    company = await _company(db_session)
    await _staff(db_session, company.id)
    reply = await build_report_reply(db_session, company.id, STAFF_CHAT)
    assert reply is not None
    assert "Firma hisoboti" in reply
    assert "Islom Xodimov" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_visible_to_operator(db_session: AsyncSession):
    company = await _company(db_session)
    await _staff(db_session, company.id, role=UserRole.OPERATOR)
    assert await build_report_reply(db_session, company.id, STAFF_CHAT) is not None
    await db_session.rollback()


# --------------------------------------------------------------------------
# /hisobot — mazmuni
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_counts_tours_and_bookings(db_session: AsyncSession):
    company = await _company(db_session)
    staff = await _staff(db_session, company.id)

    active = Tour(company_id=company.id, title="Antalya", description="x",
                  city="Antalya", price=1000, available_slots=10, is_active=True)
    inactive = Tour(company_id=company.id, title="Dubay", description="x",
                    city="Dubay", price=2000, available_slots=10, is_active=False)
    db_session.add_all([active, inactive])
    await db_session.flush()

    db_session.add_all([
        Booking(tour_id=active.id, company_id=company.id, user_id=staff.id, guests_count=2,
                total_price=5_000_000, status=BookingStatus.CONFIRMED),
        Booking(tour_id=active.id, company_id=company.id, user_id=staff.id, guests_count=1,
                total_price=2_000_000, status=BookingStatus.CONFIRMED),
        Booking(tour_id=active.id, company_id=company.id, user_id=staff.id, guests_count=1,
                total_price=1_000_000, status=BookingStatus.PENDING),
    ])
    await db_session.flush()

    reply = await build_report_reply(db_session, company.id, STAFF_CHAT)
    assert "Jami: 2 ta" in reply          # turlar
    assert "Faol: 1 ta" in reply
    assert "Tasdiqlangan: 2 ta" in reply
    assert "Kutilmoqda: 1 ta" in reply
    # Daromad faqat tasdiqlangan bronlardan: 5 mln + 2 mln
    assert "7 000 000" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_excludes_other_company_bookings(db_session: AsyncSession):
    """A ning hisobotida B ning bronlari bo'lmasin."""
    a = await _company(db_session, slug="agent-a", name="A")
    b = await _company(db_session, slug="agent-b", name="B")
    staff_a = await _staff(db_session, a.id, email="a@test.uz")
    staff_b = await _staff(db_session, b.id, chat_id="777", email="b@test.uz")

    tour_a = Tour(company_id=a.id, title="A turi", description="x",
                  city="Antalya", price=1000, available_slots=10, is_active=True)
    tour_b = Tour(company_id=b.id, title="B turi", description="x",
                  city="Dubay", price=1000, available_slots=10, is_active=True)
    db_session.add_all([tour_a, tour_b])
    await db_session.flush()
    db_session.add_all([
        Booking(tour_id=tour_a.id, company_id=a.id, user_id=staff_a.id, guests_count=1,
                total_price=1_000_000, status=BookingStatus.CONFIRMED),
        Booking(tour_id=tour_b.id, company_id=b.id, user_id=staff_b.id, guests_count=1,
                total_price=9_000_000, status=BookingStatus.CONFIRMED),
    ])
    await db_session.flush()

    reply = await build_report_reply(db_session, a.id, STAFF_CHAT)
    assert "1 000 000" in reply
    assert "9 000 000" not in reply, "B ning daromadi A ga ko'rindi"
    assert "B turi" not in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_lists_top_tours(db_session: AsyncSession):
    company = await _company(db_session)
    staff = await _staff(db_session, company.id)
    tour = Tour(company_id=company.id, title="Antalya lyuks", description="x",
                city="Antalya", price=1000, available_slots=10, is_active=True)
    db_session.add(tour)
    await db_session.flush()
    db_session.add(Booking(tour_id=tour.id, company_id=company.id, user_id=staff.id, guests_count=1,
                           total_price=1000, status=BookingStatus.CONFIRMED))
    await db_session.flush()

    reply = await build_report_reply(db_session, company.id, STAFF_CHAT)
    assert "Ommabop turlar" in reply
    assert "Antalya lyuks" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_report_works_with_no_data(db_session: AsyncSession):
    """Yangi firmada hisobot yiqilmasin."""
    company = await _company(db_session)
    await _staff(db_session, company.id)
    reply = await build_report_reply(db_session, company.id, STAFF_CHAT)
    assert reply is not None
    assert "Jami: 0 ta" in reply
    await db_session.rollback()


# --------------------------------------------------------------------------
# Dispetcher
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_text_passes_through(db_session: AsyncSession):
    """Boshqa matn odatdagi mijoz oqimiga o'tsin."""
    company = await _company(db_session)
    assert await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT, "salom"), SITE_URL
    ) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_empty_message_passes_through(db_session: AsyncSession):
    company = await _company(db_session)
    assert await try_handle_command(
        db_session, company.id, company, _msg(CUSTOMER_CHAT), SITE_URL
    ) is None
    await db_session.rollback()
