"""Telegram orqali price-list qabul qilish.

Bu modulning eng muhim vazifasi — **kim yuborayotganini tekshirish**.
Firma boti mijozlar bilan ishlaydi; tekshiruvsiz istalgan mijoz soxta narx
yuborib firmaning narx bazasini buza olardi, va agent o'sha soxta narx
bo'yicha mijozga taklif berardi.

Shuning uchun testlarning yarmi "kim qabul qilinadi, kim qilinmaydi" haqida.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, CompanyStatus
from app.models.tour_offer import OfferSource, TourOffer
from app.models.user import User, UserRole
from app.services.telegram_pricelist import (
    MIN_TEXT_LEN,
    find_staff,
    link_staff,
    try_handle_pricelist,
)
from app.utils.security import hash_password

TOKEN = "123:FAKE"
STAFF_CHAT = "555000111"
CUSTOMER_CHAT = "999888777"

PRICELIST = """
ANTALYA 7 kecha
Rixos Downtown 5* UAI — $850
Delphin Imperial 5* AI — $720
"""


def _message(chat_id, text=None, document=None, caption=None) -> dict:
    message: dict = {"chat": {"id": chat_id}}
    if text is not None:
        message["text"] = text
    if caption is not None:
        message["caption"] = caption
    if document is not None:
        message["document"] = document
    return message


async def _make_company(db: AsyncSession, slug: str = "agentlik") -> Company:
    company = Company(
        name=slug.title(), slug=slug, city="Toshkent", phone="998900000000",
        email=f"{slug}@test.uz", status=CompanyStatus.APPROVED, tariff="boshlangich",
    )
    db.add(company)
    await db.flush()
    return company


async def _make_user(
    db: AsyncSession, company_id, role=UserRole.ADMIN, chat_id=STAFF_CHAT,
    email="xodim@test.uz", password="parol123", is_active=True,
) -> User:
    user = User(
        email=email, hashed_password=hash_password(password), full_name="Xodim",
        role=role, company_id=company_id, telegram_chat_id=chat_id,
        is_active=is_active,
    )
    db.add(user)
    await db.flush()
    return user


# --------------------------------------------------------------------------
# Kim xodim
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_find_staff_accepts_own_admin(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    assert await find_staff(db_session, company.id, STAFF_CHAT) is not None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_find_staff_rejects_other_company_staff(db_session: AsyncSession):
    """Boshqa firmaning xodimi shu firma botiga narx yubora olmasin."""
    a = await _make_company(db_session, "agent-a")
    b = await _make_company(db_session, "agent-b")
    await _make_user(db_session, b.id)
    assert await find_staff(db_session, a.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_find_staff_rejects_plain_user(db_session: AsyncSession):
    """Mijoz roli (USER) xodim emas."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, role=UserRole.USER)
    assert await find_staff(db_session, company.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_find_staff_rejects_inactive(db_session: AsyncSession):
    """Ishdan bo'shatilgan xodim narx yubora olmasin."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, is_active=False)
    assert await find_staff(db_session, company.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_find_staff_rejects_unlinked_chat(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    assert await find_staff(db_session, company.id, CUSTOMER_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_operator_role_accepted(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, role=UserRole.OPERATOR)
    assert await find_staff(db_session, company.id, STAFF_CHAT) is not None
    await db_session.rollback()


# --------------------------------------------------------------------------
# Bog'lanish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_link_binds_chat(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, chat_id=None)

    reply = await link_staff(
        db_session, company.id, STAFF_CHAT, "/link xodim@test.uz parol123"
    )
    assert "bog'landi" in reply
    assert await find_staff(db_session, company.id, STAFF_CHAT) is not None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_link_rejects_wrong_password(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, chat_id=None)
    reply = await link_staff(
        db_session, company.id, STAFF_CHAT, "/link xodim@test.uz notogri"
    )
    assert "noto'g'ri" in reply
    assert await find_staff(db_session, company.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_link_rejects_other_company_user(db_session: AsyncSession):
    """Parol to'g'ri bo'lsa ham, boshqa firma xodimi bog'lanmasin."""
    a = await _make_company(db_session, "agent-a")
    b = await _make_company(db_session, "agent-b")
    await _make_user(db_session, b.id, chat_id=None)

    reply = await link_staff(
        db_session, a.id, STAFF_CHAT, "/link xodim@test.uz parol123"
    )
    assert "noto'g'ri" in reply
    assert await find_staff(db_session, a.id, STAFF_CHAT) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_link_same_reply_for_missing_and_wrong(db_session: AsyncSession):
    """Javob bir xil — qaysi email mavjudligi oshkor bo'lmasin."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, chat_id=None)

    wrong_password = await link_staff(
        db_session, company.id, STAFF_CHAT, "/link xodim@test.uz notogri"
    )
    unknown_email = await link_staff(
        db_session, company.id, STAFF_CHAT, "/link yoq@test.uz parol123"
    )
    assert wrong_password == unknown_email
    await db_session.rollback()


@pytest.mark.asyncio
async def test_link_without_args_shows_help(db_session: AsyncSession):
    company = await _make_company(db_session)
    reply = await link_staff(db_session, company.id, STAFF_CHAT, "/link")
    assert "/link email parol" in reply
    await db_session.rollback()


# --------------------------------------------------------------------------
# Price-list qabul qilish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_staff_text_pricelist_saved(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)

    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id, _message(STAFF_CHAT, PRICELIST)
    )
    assert reply is not None and "2" in reply

    offers = (await db_session.execute(select(TourOffer))).scalars().all()
    assert len(offers) == 2
    assert all(o.company_id == company.id for o in offers)
    assert all(o.source == OfferSource.PRICELIST for o in offers)
    await db_session.rollback()


@pytest.mark.asyncio
async def test_customer_pricelist_ignored(db_session: AsyncSession):
    """Mijoz yuborgan "price-list" bazaga TUSHMASIN.

    Bu modulning eng muhim testi: tekshiruvsiz istalgan odam soxta narx
    kiritib, agentni noto'g'ri taklif berishga majburlardi.
    """
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)

    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id, _message(CUSTOMER_CHAT, PRICELIST)
    )
    assert reply is None, "mijoz xabari price-list sifatida qabul qilindi"

    offers = (await db_session.execute(select(TourOffer))).scalars().all()
    assert offers == []
    await db_session.rollback()


@pytest.mark.asyncio
async def test_short_message_passes_through(db_session: AsyncSession):
    """Qisqa xabar — bu bron suhbati, aralashmaymiz."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id, _message(STAFF_CHAT, "salom")
    )
    assert reply is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_long_text_without_prices_passes_through(db_session: AsyncSession):
    """Xodim uzun savol yozgan bo'lishi mumkin — narx yo'q, o'tkazamiz."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    text = "x" * (MIN_TEXT_LEN + 20)
    assert await try_handle_pricelist(
        db_session, TOKEN, company.id, _message(STAFF_CHAT, text)
    ) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_unsupported_document_reports_clearly(db_session: AsyncSession):
    """Word/arxiv kabi formatlar tushunarli rad javobini olsin."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id,
        _message(STAFF_CHAT, document={
            "file_name": "shartnoma.docx", "file_id": "x", "file_size": 1000,
        }),
    )
    assert reply is not None
    assert "format" in reply.lower()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_image_document_goes_to_image_parser(db_session: AsyncSession, monkeypatch):
    """Rasm hujjat sifatida yuborilsa ham rasm tahlilchisiga tushsin.

    Operatorlar afishani ba'zan "fayl sifatida" yuboradi — Telegram uni
    `photo` emas, `document` qilib beradi.
    """
    from app.services import pricelist_image

    async def fake_ocr(content, mime):
        return "ANTALYA 7 kecha\nRixos 5* UAI — $850"

    monkeypatch.setattr(pricelist_image, "image_to_text", fake_ocr)
    monkeypatch.setattr(
        "app.services.telegram_pricelist._download",
        lambda token, file_id: _async_bytes(b"\x89PNG"),
    )

    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id,
        _message(STAFF_CHAT, document={
            "file_name": "afisha.jpg", "file_id": "x",
            "file_size": 1000, "mime_type": "image/jpeg",
        }),
    )
    assert reply is not None
    assert "1" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_telegram_photo_uses_largest_size(db_session: AsyncSession, monkeypatch):
    """Telegram rasmni bir necha o'lchamda yuboradi — eng kattasi kerak.

    Kichik nusxada matn o'qib bo'lmaydi.
    """
    from app.services import pricelist_image

    requested: list[str] = []

    async def fake_ocr(content, mime):
        return "ANTALYA 7 kecha\nRixos 5* UAI — $850"

    def fake_download(token, file_id):
        requested.append(file_id)
        return _async_bytes(b"\x89PNG")

    monkeypatch.setattr(pricelist_image, "image_to_text", fake_ocr)
    monkeypatch.setattr(
        "app.services.telegram_pricelist._download", fake_download
    )

    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    message = _message(STAFF_CHAT)
    message["photo"] = [
        {"file_id": "kichik", "file_size": 900, "width": 90},
        {"file_id": "katta", "file_size": 90_000, "width": 1280},
    ]

    await try_handle_pricelist(db_session, TOKEN, company.id, message)
    assert requested == ["katta"], "kichik nusxa yuklandi — matn o'qilmasdi"
    await db_session.rollback()


async def _async_bytes(value: bytes) -> bytes:
    return value


@pytest.mark.asyncio
async def test_oversized_document_rejected(db_session: AsyncSession):
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id,
        _message(STAFF_CHAT, document={
            "file_name": "price.xlsx", "file_id": "x",
            "file_size": 50 * 1024 * 1024,
        }),
    )
    assert "katta" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_customer_document_ignored(db_session: AsyncSession):
    """Mijoz hujjat yuborsa ham tegmaymiz."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    assert await try_handle_pricelist(
        db_session, TOKEN, company.id,
        _message(CUSTOMER_CHAT, document={
            "file_name": "price.xlsx", "file_id": "x", "file_size": 100,
        }),
    ) is None
    await db_session.rollback()


@pytest.mark.asyncio
async def test_caption_used_when_no_text(db_session: AsyncSession):
    """Forward qilingan xabar matni `caption` da bo'lishi mumkin."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id)
    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id, _message(STAFF_CHAT, caption=PRICELIST)
    )
    assert reply is not None
    assert len((await db_session.execute(select(TourOffer))).scalars().all()) == 2
    await db_session.rollback()


@pytest.mark.asyncio
async def test_link_command_works_before_binding(db_session: AsyncSession):
    """`/link` xodimlik tekshiruvidan OLDIN ishlashi kerak — aks holda
    bog'lanish umuman mumkin bo'lmasdi."""
    company = await _make_company(db_session)
    await _make_user(db_session, company.id, chat_id=None)

    reply = await try_handle_pricelist(
        db_session, TOKEN, company.id,
        _message(STAFF_CHAT, "/link xodim@test.uz parol123"),
    )
    assert "bog'landi" in reply
    await db_session.rollback()


@pytest.mark.asyncio
async def test_offers_scoped_to_sending_company(db_session: AsyncSession):
    """Narx faqat yuborgan xodimning firmasiga yozilsin."""
    a = await _make_company(db_session, "agent-a")
    b = await _make_company(db_session, "agent-b")
    await _make_user(db_session, a.id, email="a@test.uz")

    await try_handle_pricelist(
        db_session, TOKEN, a.id, _message(STAFF_CHAT, PRICELIST)
    )
    offers = (await db_session.execute(select(TourOffer))).scalars().all()
    assert offers and all(o.company_id == a.id for o in offers)
    assert not any(o.company_id == b.id for o in offers)
    await db_session.rollback()
