"""Yig'ilgan narxlar ichidan qidirish va operatorlarni taqqoslash.

Ikki narsa tekshiriladi:

1. **Bosqichma-bosqich yumshatish.** Agent "Antalya 5* UAI 7 kecha 800
   gacha" deb yozganda hamma shart bir vaqtda mos kelishi kam. Qattiq
   filtr 0 natija beradi va bu foydasiz. Lekin yumshatilgani JIM
   qolmasligi ham kerak — aks holda agent natijani so'raganiga to'liq mos
   deb o'ylab qoladi.

2. **Operatorlarni taqqoslash.** Butun tizimning ma'nosi shu: bir xil
   mehmonxonani turli operatordan yonma-yon ko'rish.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company, CompanyStatus
from app.services.offer_service import (
    group_by_hotel,
    save_offers,
    search_by_query,
)
from app.services.operator_connector import RawOffer
from app.services.tella_tour_search import extract_query


async def _company(db: AsyncSession, slug="fayz") -> Company:
    company = Company(
        name=slug.title(), slug=slug, city="Toshkent", phone="998900000000",
        email=f"{slug}@test.uz", status=CompanyStatus.APPROVED, tariff="boshlangich",
    )
    db.add(company)
    await db.flush()
    return company


def _offer(hotel, price, **kw) -> RawOffer:
    return RawOffer(
        hotel_name=hotel, price_gross=price, currency="USD",
        city=kw.get("city", "Antalya"), country=kw.get("country", "Turkiya"),
        star=kw.get("star", "5"), board=kw.get("board", "UAI"),
        nights=kw.get("nights", 7), price_net=kw.get("net"),
    )


async def _seed(db: AsyncSession, company_id: int, offers, operator: str):
    await save_offers(
        db, company_id=company_id, offers=offers, operator_name=operator
    )


# --------------------------------------------------------------------------
# Aniq moslik
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exact_match_no_relaxation(db_session: AsyncSession):
    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos Downtown", 850)], "Anur")

    offers, dropped = await search_by_query(
        db_session, company_id=company.id,
        query=extract_query("Antalya 5 yulduz UAI 7 kecha 900 dollargacha"),
    )
    assert len(offers) == 1
    assert dropped == set(), "aniq moslikda hech narsa yumshatilmasin"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_price_ceiling_respected(db_session: AsyncSession):
    company = await _company(db_session)
    await _seed(db_session, company.id, [
        _offer("Arzon", 500), _offer("Qimmat", 1500),
    ], "Anur")

    offers, dropped = await search_by_query(
        db_session, company_id=company.id,
        query=extract_query("Antalya 800 dollargacha"),
    )
    assert [o.hotel_name for o in offers] == ["Arzon"]
    assert "price" not in dropped
    await db_session.rollback()


# --------------------------------------------------------------------------
# Yumshatish
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_relaxes_nights_first(db_session: AsyncSession):
    """Kecha eng avval olib tashlanadi — u eng ko'p farq qiladigan shart."""
    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos", 850, nights=7)], "Anur")

    offers, dropped = await search_by_query(
        db_session, company_id=company.id,
        query=extract_query("Antalya 5 yulduz UAI 3 kecha"),
    )
    assert len(offers) == 1
    assert dropped == {"nights"}
    await db_session.rollback()


@pytest.mark.asyncio
async def test_destination_never_relaxed_when_data_absent(db_session: AsyncSession):
    """Yo'nalish umuman boshqa bo'lsa natija bermaslik TO'G'RI.

    Dubay so'ralganda Antalya taklifini ko'rsatish — noto'g'ri javob.
    """
    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos", 850)], "Anur")

    offers, _ = await search_by_query(
        db_session, company_id=company.id, query=extract_query("Dubayga 5 yulduz"),
    )
    assert offers == []
    await db_session.rollback()


@pytest.mark.asyncio
async def test_relaxation_is_reported(db_session: AsyncSession):
    """Yumshatilgani qaytarilsin — agentga aytish uchun."""
    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos", 850, star="4")], "Anur")

    _, dropped = await search_by_query(
        db_session, company_id=company.id,
        query=extract_query("Antalya 5 yulduz UAI 7 kecha"),
    )
    assert "star" in dropped
    await db_session.rollback()


# --------------------------------------------------------------------------
# Ajratilganlik
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_scoped_to_company(db_session: AsyncSession):
    a = await _company(db_session, "agent-a")
    b = await _company(db_session, "agent-b")
    await _seed(db_session, a.id, [_offer("A oteli", 850)], "Anur")
    await _seed(db_session, b.id, [_offer("B oteli", 850)], "Anur")

    offers, _ = await search_by_query(
        db_session, company_id=a.id, query=extract_query("Antalya 5 yulduz"),
    )
    assert [o.hotel_name for o in offers] == ["A oteli"]
    await db_session.rollback()


# --------------------------------------------------------------------------
# Operatorlarni taqqoslash
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_same_hotel_from_two_operators_grouped(db_session: AsyncSession):
    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos Downtown", 850)], "Anur Tour")
    await _seed(db_session, company.id, [_offer("Rixos Downtown", 790)], "Asia Luxe")

    offers, _ = await search_by_query(
        db_session, company_id=company.id, query=extract_query("Antalya 5 yulduz"),
    )
    groups = group_by_hotel(offers)
    assert len(groups) == 1, "bir mehmonxona ikki guruhga bo'lindi"
    assert len(groups[0]) == 2
    assert groups[0][0].price_gross == 790, "arzoni birinchi turishi kerak"
    await db_session.rollback()


def test_grouping_normalises_hotel_name():
    """Operatorlar nomni turlicha yozadi — "RIXOS  DOWNTOWN" va
    "Rixos Downtown" bitta mehmonxona."""
    from app.models.tour_offer import TourOffer

    a = TourOffer(company_id=1, hotel_name="Rixos Downtown", nights=7,
                  board="UAI", price_gross=850, currency="USD")
    b = TourOffer(company_id=1, hotel_name="RIXOS  DOWNTOWN", nights=7,
                  board="UAI", price_gross=790, currency="USD")
    assert len(group_by_hotel([a, b])) == 1


def test_different_board_not_grouped():
    """Bir mehmonxona, boshqa ovqat — bu boshqa taklif, taqqoslanmasin."""
    from app.models.tour_offer import TourOffer

    a = TourOffer(company_id=1, hotel_name="Rixos", nights=7, board="UAI",
                  price_gross=850, currency="USD")
    b = TourOffer(company_id=1, hotel_name="Rixos", nights=7, board="BB",
                  price_gross=500, currency="USD")
    assert len(group_by_hotel([a, b])) == 2


def test_multi_operator_groups_come_first():
    """Tanlov bor guruh yuqorida — taqqoslash imkoni shu yerda."""
    from app.models.tour_offer import TourOffer

    single = TourOffer(company_id=1, hotel_name="Yolgiz", nights=7, board="AI",
                       price_gross=400, currency="USD")
    a = TourOffer(company_id=1, hotel_name="Ikkitali", nights=7, board="AI",
                  price_gross=900, currency="USD")
    b = TourOffer(company_id=1, hotel_name="Ikkitali", nights=7, board="AI",
                  price_gross=880, currency="USD")

    groups = group_by_hotel([single, a, b])
    assert groups[0][0].hotel_name == "Ikkitali"


# --------------------------------------------------------------------------
# Tella javobi
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tella_reply_shows_comparison(db_session: AsyncSession):
    from app.services.ml_assistant import _start_tour_search

    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos Downtown", 850)], "Anur Tour")
    await _seed(db_session, company.id, [_offer("Rixos Downtown", 790)], "Asia Luxe")

    reply = await _start_tour_search(
        db_session, company.id, "Antalyaga 5 yulduz UAI qidir"
    )
    text = reply["reply"]
    assert "Rixos Downtown" in text
    assert "790" in text and "850" in text
    assert "Anur Tour" in text and "Asia Luxe" in text
    assert "2 operatorda bor" in text
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tella_reply_warns_about_relaxation(db_session: AsyncSession):
    """Yumshatilgani jim qolmasin."""
    from app.services.ml_assistant import _start_tour_search

    company = await _company(db_session)
    await _seed(db_session, company.id, [_offer("Rixos", 850, star="4")], "Anur")

    reply = await _start_tour_search(
        db_session, company.id, "Antalyaga 5 yulduz qidir"
    )
    assert "yulduz" in reply["reply"]
    assert "olib tashlandi" in reply["reply"]
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tella_reply_when_nothing_found(db_session: AsyncSession):
    from app.services.ml_assistant import _start_tour_search

    company = await _company(db_session)
    reply = await _start_tour_search(db_session, company.id, "Dubayga tur qidir")
    assert "topilmadi" in reply["reply"]
    assert "Narxlar" in reply["reply"], "nima qilishni aytsin"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tella_asks_for_destination(db_session: AsyncSession):
    from app.services.ml_assistant import _start_tour_search

    company = await _company(db_session)
    reply = await _start_tour_search(db_session, company.id, "7 kecha 2 kishi qidir")
    assert "yo'nalish" in reply["reply"].lower()
    assert reply["pending"]["stage"] == "collect"
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tella_shows_agent_margin(db_session: AsyncSession):
    """Foyda ko'rsatilsin — agent uchun asosiy raqam shu."""
    from app.services.ml_assistant import _start_tour_search

    company = await _company(db_session)
    await _seed(db_session, company.id,
                [_offer("Rixos", 850, net=780)], "Anur Tour")

    reply = await _start_tour_search(db_session, company.id, "Antalya qidir")
    assert "foyda" in reply["reply"]
    assert "70" in reply["reply"]
    await db_session.rollback()
