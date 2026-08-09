"""Psixologik profil + erkin matn -> tur paket tavsiyasi.

Ikkita manba birlashtiriladi:
  * anketa (`travel_profile`) — odam QANDAY dam olishni yoqtiradi;
  * suhbat (`tella_tour_search`) — byudjet, sana, necha kishi, qayerga.

Anketa "qanday", suhbat "qachon va qancha" degan savolga javob beradi.
Ikkalasi ham majburiy emas: birortasi bo'lmasa ham ro'yxat qaytadi,
shunchaki tartibi kamroq aniq bo'ladi.

MEHMONXONA BLOKI YO'Q — faqat tur paket. Mijoz bron qiladi, agentlik
tasdiqlaydi, holat real vaqtda almashadi va yozishuv ochiladi.

Faqat RUXSAT BERGAN agentliklarning turlari chiqadi
(`companies.recommender_enabled`). Ruxsat bermagan firma katalogda
qoladi, lekin tavsiyaga tushmaydi.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, CompanyStatus
from app.models.recommendation_event import RecommendationEvent
from app.models.tour import Tour
from app.services import tour_taxonomy
from app.services.currency import to_uzs
from app.services.tella_tour_search import (
    TourSearchQuery,
    extract_query,
    next_question,
)
from app.services.travel_profile import (
    DIMENSIONS,
    Preference,
    TravelProfile,
    explain,
    score,
    to_preference,
)

# Ball og'irliklari. Ochiq turadi, chunki keyingi qadamda ular
# `recommendation_events` bo'yicha sozlanadi.
W_CATEGORY_FIRST = 40.0     # profil aytgan BIRINCHI toifa
W_CATEGORY_OTHER = 22.0     # qolgan toifalar
W_BOOKING_TYPE = 15.0
W_DURATION = 12.0
W_DESTINATION = 35.0        # mijoz nomini AYTGAN yo'nalish
W_CATEGORY_SAID = 45.0      # mijoz AYTGAN toifa ("dengizga")
W_BUDGET = 25.0
W_DEPARTURE = 18.0          # o'z shahridan jo'naydi
W_POPULAR = 6.0
logger = logging.getLogger(__name__)

# Ball og'irliklari (davomi)
W_LEARNED = 30.0          # tarixdan o'rganilgan moslik


@dataclass
class Suggestion:
    tour: Tour
    score: float
    # Nega shu tur — mijozga ko'rsatiladi.
    matched: list[str]

    def to_dict(self, lang: str = "uz") -> dict:
        t = self.tour
        firma = t.__dict__.get("company")
        return {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "city": t.city,
            "country": t.country,
            "departure_city": t.departure_city or (firma.city if firma else None),
            "price": t.price,
            "currency": t.currency or "UZS",
            "duration_days": t.duration_days,
            "start_date": t.start_date.isoformat() if t.start_date else None,
            "available_slots": t.available_slots,
            "image_url": t.image_url,
            "booking_type": t.booking_type or "group",
            "company_id": t.company_id,
            "company_name": firma.name if firma else None,
            "match_score": round(self.score, 1),
            "matched": self.matched,
        }


def _tour_text(t: Tour) -> str:
    """Toifani aniqlash uchun matn.

    Turda alohida `category` ustuni yo'q — agentliklar uni to'ldirmaydi.
    Sarlavha va tavsif esa har doim bor, taksonomiya ular bo'yicha
    ishlaydi.
    """
    return f"{t.title} {t.description or ''} {t.city} {t.country}"


def _duration_fits(days: int, pref: Preference) -> bool:
    return pref.min_days <= days <= pref.max_days


def _similarity(profile: TravelProfile, markaz: dict[str, float]) -> float:
    """Profil va o'rganilgan markaz orasidagi yaqinlik, 0..1.

    Evklid masofasi to'rt o'lchamda eng ko'pi bilan 2 (har biri 0..1),
    shuning uchun shunga bo'lamiz. Yarmidan uzoq bo'lsa nol qaytaramiz —
    "biroz o'xshash" tavsiyani kuchaytirmasligi kerak.
    """
    kvadrat = sum(
        (profile.get(d) - markaz.get(d, 0.5)) ** 2 for d in DIMENSIONS
    )
    masofa = math.sqrt(kvadrat) / 2.0
    return max(0.0, 1.0 - masofa * 2.0)


def rank(
    tours: list[Tour],
    pref: Preference,
    query: Optional[TourSearchQuery] = None,
    departure_city: Optional[str] = None,
    profile: Optional[TravelProfile] = None,
    learned: Optional[dict[str, dict[str, float]]] = None,
) -> list[Suggestion]:
    """Turlarni moslik bo'yicha saralaydi.

    Toza funksiya — bazasiz sinaladi.

    Turlar FILTRLANMAYDI, faqat tartiblanadi: mijoz aytgan shartga to'liq
    mos tur bo'lmasa ham bo'sh ro'yxat ko'rsatishdan ko'ra eng yaqinini
    ko'rsatgan ma'qul.

    `learned` — haqiqiy bronlardan chiqqan toifa markazlari
    (`learned_centroids`). Berilmasa faqat qo'lda yozilgan qoidalar
    ishlaydi; ya'ni tarix bo'lmasa tizim eskicha, lekin ishlaydigan
    holatda qoladi.
    """
    natija: list[Suggestion] = []
    mamlakatlar = {d.country_code for d in (query.destinations if query else [])}
    shaharlar = {
        tour_taxonomy.normalize(d.name_uz)
        for d in (query.destinations if query else [])
    }

    for t in tours:
        ball = 0.0
        sabab: list[str] = []

        toifa = tour_taxonomy.match_category(_tour_text(t))
        if toifa is not None and toifa in pref.categories:
            birinchi = pref.categories[0] == toifa
            ball += W_CATEGORY_FIRST if birinchi else W_CATEGORY_OTHER
            sabab.append(f"toifa:{toifa.value}")

        # Tarixdan o'rganilgan moslik. Qoidalarni ALMASHTIRMAYDI,
        # ustiga qo'shiladi: yangi toifada tarix bo'lmasa qoidalar
        # baribir ishlaydi.
        if profile is not None and learned and toifa is not None:
            markaz = learned.get(toifa.value)
            if markaz:
                yaqinlik = _similarity(profile, markaz)
                if yaqinlik > 0:
                    ball += W_LEARNED * yaqinlik
                    sabab.append("tarix")

        if (t.booking_type or "group") == pref.booking_type:
            ball += W_BOOKING_TYPE
            sabab.append(f"turi:{pref.booking_type}")

        if _duration_fits(t.duration_days or 0, pref):
            ball += W_DURATION
            sabab.append("davomiylik")

        if query is not None:
            # Mijoz toifani O'ZI aytgan bo'lsa ("dengizga", "umraga") u
            # anketadan ustun turadi: anketa odamning odatini taxmin
            # qiladi, bu esa hozirgi aniq niyati.
            if query.category is not None and toifa == query.category:
                ball += W_CATEGORY_SAID
                sabab.append("aytgan_toifa")

            shahar_n = tour_taxonomy.normalize(t.city or "")
            if shahar_n and shahar_n in shaharlar:
                ball += W_DESTINATION
                sabab.append("yonalish")
            elif mamlakatlar:
                # Mamlakat kodi turda saqlanmaydi, nomi bo'yicha
                # taqqoslaymiz.
                mos = tour_taxonomy.match_destinations(
                    f"{t.city} {t.country}"
                )
                if any(d.country_code in mamlakatlar for d in mos):
                    ball += W_DESTINATION * 0.6
                    sabab.append("mamlakat")

            if query.budget_max is not None:
                narx = t.price_uzs or to_uzs(t.price, t.currency or "UZS")
                chegara = query.budget_max
                if query.currency and query.currency != "UZS":
                    chegara = to_uzs(query.budget_max, query.currency)
                if narx <= chegara:
                    ball += W_BUDGET
                    sabab.append("byudjet")
                elif narx <= chegara * 1.2:
                    # Ozgina oshgani darrov chiqarib tashlanmaydi:
                    # mijozlar byudjetni taxminan aytadi.
                    ball += W_BUDGET * 0.4
                    sabab.append("byudjet_yaqin")

            if query.nights is not None and t.duration_days:
                farq = abs(t.duration_days - query.nights)
                if farq <= 1:
                    ball += W_DURATION
                    sabab.append("kechalar")

        if departure_city:
            jonash = t.departure_city or (
                t.__dict__.get("company").city
                if t.__dict__.get("company") else None
            )
            if jonash and tour_taxonomy.normalize(jonash) == \
                    tour_taxonomy.normalize(departure_city):
                ball += W_DEPARTURE
                sabab.append("shahringizdan")

        # Joy qolmagan turni yuqoriga chiqarish mijozni bekorga
        # umidvor qiladi.
        if (t.available_slots or 0) <= 0:
            ball -= 50.0
        elif t.available_slots <= 3:
            ball += W_POPULAR   # kam qolgani — tanlov bosimi emas, haqiqat

        natija.append(Suggestion(tour=t, score=ball, matched=sabab))

    natija.sort(key=lambda s: (-s.score, s.tour.price_uzs or float("inf")))
    return natija


# O'rganilgan markazlar keshi. Har so'rovda bazaga qayta bormaslik
# uchun: ular sekin o'zgaradi (bron kunlab yig'iladi), lekin tavsiya
# sahifasi tez-tez ochiladi.
_CENTROID_TTL = 10 * 60
_MIN_SAMPLES = 5
_kesh: dict[str, dict[str, float]] = {}
_kesh_vaqti: float = 0.0


async def learned_centroids(
    db: AsyncSession, force: bool = False
) -> dict[str, dict[str, float]]:
    """Haqiqiy bronlardan toifa markazlarini hisoblaydi.

    Har toifa uchun uni BRON QILGAN odamlarning o'rtacha profili. Yangi
    mijoz shu markazga qanchalik yaqin bo'lsa, o'sha toifa shunchalik
    yuqoriga chiqadi.

    `_MIN_SAMPLES` dan kam bron bo'lgan toifa TASHLANADI: bitta-ikkita
    tasodifiy tanlov butun tavsiyani buzib qo'yardi. Ya'ni tizim
    o'rganishni faqat yetarli dalil to'planganda boshlaydi.
    """
    global _kesh, _kesh_vaqti
    hozir = time.monotonic()
    if not force and _kesh_vaqti and hozir - _kesh_vaqti < _CENTROID_TTL:
        return _kesh

    stmt = (
        select(
            RecommendationEvent.category,
            func.avg(RecommendationEvent.sokinlik),
            func.avg(RecommendationEvent.yangilik),
            func.avg(RecommendationEvent.davra),
            func.avg(RecommendationEvent.tartib),
            func.count(RecommendationEvent.id),
        )
        .where(
            RecommendationEvent.outcome == "booked",
            RecommendationEvent.category.is_not(None),
        )
        .group_by(RecommendationEvent.category)
    )
    try:
        qatorlar = (await db.execute(stmt)).all()
    except Exception as exc:
        # Jadval hali yaratilmagan bo'lishi mumkin — tavsiya baribir
        # ishlashda davom etsin.
        logger.warning("markazlarni o'qib bo'lmadi: %s", exc)
        return _kesh

    yangi: dict[str, dict[str, float]] = {}
    for toifa, sok, yan, dav, tar, soni in qatorlar:
        if soni < _MIN_SAMPLES:
            continue
        yangi[toifa] = {
            "sokinlik": float(sok or 0.5),
            "yangilik": float(yan or 0.5),
            "davra": float(dav or 0.5),
            "tartib": float(tar or 0.5),
        }
    _kesh = yangi
    _kesh_vaqti = hozir
    return _kesh


async def log_event(
    db: AsyncSession,
    profile: TravelProfile,
    tour: Optional[Tour],
    outcome: str,
    user_id: Optional[int] = None,
    position: Optional[int] = None,
) -> None:
    """Tavsiya natijasini yozadi.

    Yozuv MUVAFFAQIYATSIZ bo'lsa ham chaqiruvchi yiqilmaydi: statistika
    mijozning bron qilishidan muhimroq emas.
    """
    try:
        toifa = (
            tour_taxonomy.match_category(_tour_text(tour)) if tour else None
        )
        db.add(
            RecommendationEvent(
                user_id=user_id,
                tour_id=tour.id if tour else None,
                company_id=tour.company_id if tour else None,
                sokinlik=profile.get("sokinlik"),
                yangilik=profile.get("yangilik"),
                davra=profile.get("davra"),
                tartib=profile.get("tartib"),
                category=toifa.value if toifa else None,
                position=position,
                outcome=outcome,
            )
        )
        await db.flush()
    except Exception as exc:
        logger.warning("tavsiya hodisasi yozilmadi: %s", exc)


async def recommend(
    db: AsyncSession,
    answers: Optional[dict[str, str]] = None,
    text: str = "",
    departure_city: Optional[str] = None,
    limit: int = 10,
    lang: str = "uz",
    user_id: Optional[int] = None,
    log_shown: int = 5,
) -> dict:
    """Anketa va matndan tur tavsiya qiladi.

    Ko'rsatilgan birinchi `log_shown` ta tur `recommendation_events` ga
    yoziladi — keyin bron bilan solishtirib o'rganish uchun. Yozuv shu
    yerda qilinadi, chunki ORM obyektlari qo'lda: routerda qilinsa har
    tur uchun bazaga qayta borishga to'g'ri kelardi.
    """
    profile: TravelProfile = score(answers or {})
    pref = to_preference(profile)
    query = extract_query(text) if text.strip() else None

    stmt = (
        select(Tour)
        .options(selectinload(Tour.company))
        .join(Company, Tour.company_id == Company.id)
        .where(
            Tour.is_active.is_(True),
            # Ruxsat bergan va faol agentliklar.
            Company.recommender_enabled.is_(True),
            Company.status == CompanyStatus.APPROVED,
        )
        # Bir necha yuz turdan ortig'ini xotiraga olmaymiz: saralash
        # Python tarafida, chunki ballar SQL'da ifodalanmaydi.
        .limit(400)
    )
    tours = list((await db.execute(stmt)).scalars().all())
    markazlar = await learned_centroids(db)
    tartibli = rank(
        tours, pref, query, departure_city,
        profile=profile, learned=markazlar,
    )

    # Anketa to'ldirilmagan bo'lsa yozmaymiz: hamma o'lchami 0.5 bo'lgan
    # profil hech nima o'rgatmaydi, jadvalni esa har sahifa ochilishida
    # beshta qatorga to'ldiradi.
    if profile.answered:
        for i, s in enumerate(tartibli[:log_shown]):
            await log_event(db, profile, s.tour, "shown",
                            user_id=user_id, position=i)

    return {
        "profile": profile.to_dict(),
        "preference": {
            "categories": [c.value for c in pref.categories],
            "booking_type": pref.booking_type,
            "min_days": pref.min_days,
            "max_days": pref.max_days,
        },
        "reasons": explain(pref, lang),
        "query": query.to_dict() if query else None,
        "items": [s.to_dict(lang) for s in tartibli[:limit]],
        "total": len(tartibli),
        "learned_categories": sorted(markazlar),
    }


# Suhbat javoblari. Uch tilda va SHABLONSIZ emas — mijoz nima aytganini
# takrorlab tasdiqlaymiz, aks holda odam eshitilmagandek his qiladi.
_REPLY: dict[str, dict[str, str]] = {
    "uz": {
        "tushundim": "Tushundim: {xulosa}.",
        "topildi": "Sizga mos {n} ta tur paket topdim.",
        "topilmadi": (
            "Aynan shu shartlarga mos tur hozircha yo'q. "
            "Eng yaqin variantlarni ko'rsataman."
        ),
        "anketa": "Anketani to'ldirsangiz tanlovni aniqroq qilaman.",
    },
    "ru": {
        "tushundim": "Понял: {xulosa}.",
        "topildi": "Нашёл {n} подходящих турпакетов.",
        "topilmadi": (
            "Точного совпадения пока нет. "
            "Покажу самые близкие варианты."
        ),
        "anketa": "Заполните анкету — подберу точнее.",
    },
    "en": {
        "tushundim": "Got it: {xulosa}.",
        "topildi": "I found {n} matching tour packages.",
        "topilmadi": (
            "No exact match yet. I will show the closest options."
        ),
        "anketa": "Fill in the questionnaire and I will narrow it down.",
    },
}


def compose_reply(
    message: str,
    query: Optional[TourSearchQuery],
    reasons: list[str],
    found: int,
    answered: int,
    lang: str = "uz",
) -> str:
    """Suhbat javobi.

    Tashqi model yo'q: matndan olingan ma'lumot takrorlanadi, yetmagani
    so'raladi va natija aytiladi. Ortiqcha "quvnoq" gaplar yozilmaydi —
    mijozga javob kerak, suhbatdosh emas.
    """
    til = lang if lang in _REPLY else "uz"
    m = _REPLY[til]
    qismlar: list[str] = []

    if query is not None:
        from app.services.tella_tour_search import summarize

        xulosa = summarize(query)
        if xulosa:
            qismlar.append(m["tushundim"].format(xulosa=xulosa))

    qismlar.append(
        m["topildi"].format(n=found) if found else m["topilmadi"]
    )

    # Profil sabablari — nega aynan shunday tanlanganini aytamiz.
    if reasons:
        qismlar.append(reasons[0] + ".")
    elif answered == 0:
        qismlar.append(m["anketa"])

    # Yetishmayotgan ma'lumot bo'lsa bittasini so'raymiz. Bir vaqtda
    # bir nechta savol berish suhbatni so'roqqa aylantiradi.
    if query is not None:
        savol = next_question(query)
        if savol:
            qismlar.append(savol)

    return " ".join(qismlar)
