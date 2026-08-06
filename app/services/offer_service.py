"""Topilgan takliflarni saqlash va o'qish — hammasi turagent bo'yicha.

Har bir funksiya `company_id` ni **majburiy argument** sifatida oladi.
Ataylab shunday: ixtiyoriy bo'lsa yoki obyektdan olinsa, bir joyda unutilib
qolishi va bir turagentning narxi boshqasiga ko'rinib ketishi mumkin.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tour_offer import OfferSource, TourOffer
from app.services.operator_connector import RawOffer

# Price-list narxi jonli qidiruvdan uzoqroq yashaydi: operator uni bir
# necha kunga e'lon qiladi. Jonli qidiruv natijasi esa soatlar ichida
# eskiradi.
TTL_HOURS: dict[str, int] = {
    OfferSource.PRICELIST: 24 * 7,
    OfferSource.CABINET: 24 * 7,
    OfferSource.RFQ: 24 * 3,
    OfferSource.RPA: 6,
    OfferSource.EXTENSION: 6,
    OfferSource.MANUAL: 24 * 30,
}

# Manba qanchalik ishonchli. Bir xil mehmonxona turli kanaldan kelsa
# reytingda shu hisobga olinadi.
CONFIDENCE: dict[str, float] = {
    OfferSource.RPA: 0.95,
    OfferSource.EXTENSION: 0.95,
    OfferSource.CABINET: 0.9,
    OfferSource.RFQ: 0.85,
    OfferSource.PRICELIST: 0.7,
    OfferSource.MANUAL: 0.6,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def save_offers(
    db: AsyncSession,
    *,
    company_id: int,
    offers: Iterable[RawOffer],
    source: str = OfferSource.PRICELIST,
    operator_id: Optional[int] = None,
    operator_name: Optional[str] = None,
    search_id: Optional[int] = None,
) -> list[TourOffer]:
    """Xom takliflarni bazaga yozadi.

    Eskilari O'CHIRILMAYDI — `expires_at` qo'yiladi va so'rovlarda
    filtrlanadi. Yig'ilgan narx tarixi vaqt o'tib platformaning eng
    qimmatli aktiviga aylanadi.
    """
    ttl = timedelta(hours=TTL_HOURS.get(source, 24))
    expires_at = _now() + ttl
    confidence = CONFIDENCE.get(source, 0.5)

    saved: list[TourOffer] = []
    for raw in offers:
        if not raw.hotel_name:
            continue
        offer = TourOffer(
            company_id=company_id,
            search_id=search_id,
            operator_id=operator_id,
            operator_name=operator_name,
            hotel_name=raw.hotel_name[:300],
            city=raw.city,
            country=raw.country,
            star=raw.star,
            board=raw.board,
            room=raw.room,
            date_from=raw.date_from,
            nights=raw.nights,
            adults=raw.adults,
            children=raw.children,
            price_gross=raw.price_gross,
            price_net=raw.price_net,
            currency=raw.currency or "USD",
            commission_pct=raw.commission_pct,
            flight_included=raw.flight_included,
            transfer_included=raw.transfer_included,
            source=source,
            confidence=confidence,
            deep_link=raw.deep_link,
            raw=str(raw.raw) if raw.raw else None,
            expires_at=expires_at,
        )
        db.add(offer)
        saved.append(offer)

    await db.flush()
    return saved


async def list_offers(
    db: AsyncSession,
    *,
    company_id: int,
    country: Optional[str] = None,
    city: Optional[str] = None,
    board: Optional[str] = None,
    star: Optional[str] = None,
    nights: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    only_fresh: bool = True,
    saved_only: bool = False,
    limit: int = 100,
) -> list[TourOffer]:
    """Turagentning takliflarini filtrlab qaytaradi.

    Tartiblash **eng arzon narx bo'yicha emas** — agentga qoladigan foyda
    bo'yicha. Eng arzon taklif eng ko'p daromad keltirmasligi mumkin:
    operator komissiyasi har xil.
    """
    stmt = select(TourOffer).where(TourOffer.company_id == company_id)

    if only_fresh:
        stmt = stmt.where(
            (TourOffer.expires_at.is_(None)) | (TourOffer.expires_at > _now())
        )
    if saved_only:
        stmt = stmt.where(TourOffer.is_saved.is_(True))
    if country:
        stmt = stmt.where(TourOffer.country == country)
    if city:
        stmt = stmt.where(TourOffer.city == city)
    if board:
        stmt = stmt.where(TourOffer.board == board)
    if star:
        stmt = stmt.where(TourOffer.star == star)
    if nights:
        stmt = stmt.where(TourOffer.nights == nights)
    if price_min is not None:
        stmt = stmt.where(TourOffer.price_gross >= price_min)
    if price_max is not None:
        stmt = stmt.where(TourOffer.price_gross <= price_max)

    rows = (await db.execute(stmt.limit(min(limit, 500)))).scalars().all()
    return sorted(rows, key=_ranking_key)


async def search_by_query(
    db: AsyncSession, *, company_id: int, query, limit: int = 60
) -> tuple[list[TourOffer], set[str]]:
    """`TourSearchQuery` (Tella tahlil qilgan so'rov) bo'yicha qidiradi.

    Qaytaradi: `(topilgan_takliflar, olib_tashlangan_shartlar)`. Ikkinchisi
    kerak — agentga "5 yulduz topilmadi, shuning uchun yulduz sharti olib
    tashlandi" deb aytish uchun. Jimgina boshqa natija ko'rsatish yomon:
    agent uni so'ralgan shartga mos deb o'ylaydi.

    Filtrlash **bosqichma-bosqich yumshatiladi**: qattiq qo'llansa agent
    "Antalya 5* UAI 7 kecha 800 gacha" deb yozganda ko'pincha 0 natija
    chiqadi va bu foydasiz. Avval hamma shart bilan qidiriladi, natija
    bo'lmasa eng qattiq shartdan boshlab olib tashlanadi.
    """
    cities = [d.name_uz for d in query.destinations if not d.is_country]
    countries = [d.name_uz for d in query.destinations if d.is_country]

    # Yumshatish tartibi: kecha -> ovqat -> yulduz -> narx -> kurort.
    # Yo'nalish oxirigacha saqlanadi — usiz natija umuman ma'nosiz.
    relaxations = (
        {},
        {"nights"},
        {"nights", "board"},
        {"nights", "board", "star"},
        {"nights", "board", "star", "price"},
        {"nights", "board", "star", "price", "city"},
    )

    for dropped in relaxations:
        stmt = select(TourOffer).where(
            TourOffer.company_id == company_id,
            (TourOffer.expires_at.is_(None)) | (TourOffer.expires_at > _now()),
        )

        if "city" not in dropped and cities:
            stmt = stmt.where(TourOffer.city.in_(cities))
        elif countries:
            stmt = stmt.where(
                (TourOffer.country.in_(countries)) | (TourOffer.city.in_(cities))
                if cities else TourOffer.country.in_(countries)
            )

        if "star" not in dropped and query.star:
            stmt = stmt.where(TourOffer.star == query.star)
        if "board" not in dropped and query.board:
            stmt = stmt.where(TourOffer.board == str(query.board))
        if "nights" not in dropped and query.nights:
            stmt = stmt.where(TourOffer.nights == query.nights)
        if "price" not in dropped:
            if query.budget_max is not None:
                stmt = stmt.where(TourOffer.price_gross <= query.budget_max)
            if query.budget_min is not None:
                stmt = stmt.where(TourOffer.price_gross >= query.budget_min)

        rows = (await db.execute(stmt.limit(limit))).scalars().all()
        if rows:
            return sorted(rows, key=_ranking_key), set(dropped)

    return [], set(relaxations[-1])


def group_by_hotel(offers: list[TourOffer]) -> list[list[TourOffer]]:
    """Bir xil mehmonxonani turli operatorlardan bitta guruhga yig'adi.

    Aslida butun tizimning ma'nosi shu: agent "Rixos Downtown" ni uch
    operatordan ko'rib, eng foydalisini tanlashi kerak. Tekis ro'yxatda
    ular bir-biridan uzoqda turadi va taqqoslash yo'qoladi.
    """
    buckets: dict[tuple, list[TourOffer]] = {}
    for offer in offers:
        # Mehmonxona nomi operatorlarda turlicha yoziladi ("Rixos Downtown",
        # "RIXOS DOWNTOWN 5*") — kichik harf va bo'shliqlarni tekislaymiz.
        key = (
            "".join((offer.hotel_name or "").lower().split()),
            offer.nights,
            offer.board,
        )
        buckets.setdefault(key, []).append(offer)

    groups = [sorted(items, key=_ranking_key) for items in buckets.values()]
    # Ko'p operatordan kelgan guruh yuqorida — u yerda tanlov bor.
    groups.sort(key=lambda g: (-len(g), _ranking_key(g[0])))
    return groups


def _ranking_key(offer: TourOffer) -> tuple:
    """Reyting: avval foyda, keyin narx, keyin ishonchlilik.

    Foyda noma'lum bo'lsa (netto narx berilmagan) taklif pastga tushmasin —
    shunchaki narx bo'yicha joylashadi.
    """
    margin = offer.agent_margin
    return (
        0 if margin is not None else 1,
        -(margin or 0),
        offer.price_gross if offer.price_gross is not None else float("inf"),
        -(offer.confidence or 0),
    )
