"""Har bir tur firma uchun shaxsiy AI yordamchi (Gemini).

Yordamchi FAQAT joriy firmaning malumotini koradi va oʻzgartiradi (company_id
bilan chegaralangan). U xisobotlarni oqiydi, turlar/mijozlar/bronlarni sanaydi,
yangi tur qoshadi va mavjud tur narxi/faolligini oʻzgartiradi. Ochirish yoq.

Ishlash usuli: native function-calling oʻrniga soddaroq va ishonchli JSON
protokoli. Model har qadamda bitta JSON qaytaradi — yoki tool chaqiradi
{"tool": nom, "args": {...}}, yoki foydalanuvchiga javob beradi {"reply": "..."}.
Biz toolni bajarib, natijani qaytaramiz va sikl davom etadi. Bu call_analysis
dagi ishlaydigan Gemini chaqiruvining ustiga qurilgan.
"""

import json
import logging
from datetime import date, datetime
from typing import Any, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.booking import Booking, BookingStatus
from app.models.company import Company
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.reports_service import ReportsService
from app.services.tariff import DEFAULT_TARIFF, get_tariff, within_tour_limit

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Model tool chaqirishlari soni cheklangan — cheksiz siklning oldini oladi.
_MAX_STEPS = 6
_LIST_CAP = 25


class AssistantUnavailable(RuntimeError):
    """AI kaliti sozlanmagan yoki xizmat javob bermadi."""


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key)


# --------------------------------------------------------------------------- #
# Tool'lar — hammasi company_id bilan chegaralangan. Har biri JSON qaytaradi.
# --------------------------------------------------------------------------- #

def _cur(c: Optional[str]) -> str:
    return {"USD": "$", "EUR": "€", "RUB": "₽"}.get(c or "UZS", "som")


async def _t_get_report(db: AsyncSession, cid: int, args: dict) -> dict:
    rng = str(args.get("range", "28d"))
    if rng not in ("24h", "7d", "28d", "1y", "all"):
        rng = "28d"
    ov = await ReportsService(db).overview(company_id=cid, range_key=rng)
    return {
        "sayt_tashriflari": ov.total_visits,
        "mijozlar": ov.total_users,
        "bronlar": ov.total_bookings,
        "daromad_som": ov.total_revenue,
        "kunlik_faol": ov.daily_active,
        "oylik_faol": ov.monthly_active,
        "turlar_soni": ov.total_tours,
        "top_turlar": [{"nom": t.name, "bronlar": t.bookings, "daromad": t.revenue} for t in ov.top[:5]],
    }


async def _t_count_tours(db: AsyncSession, cid: int, args: dict) -> dict:
    q = select(func.count(Tour.id)).where(Tour.company_id == cid)
    if args.get("active_only"):
        q = q.where(Tour.is_active == True)  # noqa: E712
    total = (await db.execute(q)).scalar() or 0
    return {"soni": total}


async def _t_list_tours(db: AsyncSession, cid: int, args: dict) -> dict:
    limit = min(int(args.get("limit", 20) or 20), _LIST_CAP)
    q = select(Tour).where(Tour.company_id == cid)
    if args.get("active_only"):
        q = q.where(Tour.is_active == True)  # noqa: E712
    q = q.order_by(Tour.created_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return {
        "turlar": [
            {
                "id": t.id, "nom": t.title, "shahar": t.city,
                "narx": t.price, "valyuta": _cur(t.currency),
                "joylar": t.available_slots, "kunlar": t.duration_days,
                "faol": bool(t.is_active),
            }
            for t in rows
        ]
    }


async def _t_recent_bookings(db: AsyncSession, cid: int, args: dict) -> dict:
    limit = min(int(args.get("limit", 10) or 10), _LIST_CAP)
    rows = (
        await db.execute(
            select(Booking.id, Booking.status, Booking.total_price, Booking.created_at, Tour.title)
            .join(Tour, Tour.id == Booking.tour_id)
            .where(Booking.company_id == cid)
            .order_by(Booking.created_at.desc())
            .limit(limit)
        )
    ).all()
    return {
        "bronlar": [
            {"id": r[0], "holat": r[1].value if hasattr(r[1], "value") else str(r[1]),
             "narx": float(r[2] or 0), "sana": r[3].strftime("%Y-%m-%d") if r[3] else None, "tur": r[4]}
            for r in rows
        ]
    }


async def _t_count_customers(db: AsyncSession, cid: int, args: dict) -> dict:
    total = (
        await db.execute(
            select(func.count(func.distinct(Booking.user_id))).where(Booking.company_id == cid)
        )
    ).scalar() or 0
    return {"mijozlar_soni": total}


async def _t_get_plan(db: AsyncSession, cid: int, args: dict) -> dict:
    company = (await db.execute(select(Company).where(Company.id == cid))).scalar_one_or_none()
    plan = get_tariff(getattr(company, "tariff", DEFAULT_TARIFF) if company else DEFAULT_TARIFF)
    tours_used = (await db.execute(select(func.count(Tour.id)).where(Tour.company_id == cid))).scalar() or 0
    return {
        "tarif": plan["name"],
        "max_turlar": plan.get("max_tours"),
        "ishlatilgan_turlar": tours_used,
        "max_filiallar": plan.get("max_branches"),
    }


async def _t_create_tour(db: AsyncSession, cid: int, args: dict) -> dict:
    required = ["title", "city", "price", "duration_days", "available_slots"]
    missing = [f for f in required if args.get(f) in (None, "")]
    if missing:
        return {"error": f"Quyidagi maydonlar yetishmayapti: {', '.join(missing)}"}

    try:
        price = float(args["price"])
        duration = int(args["duration_days"])
        slots = int(args["available_slots"])
    except (TypeError, ValueError):
        return {"error": "narx, kunlar va joylar son bolishi kerak"}
    if price <= 0 or duration < 1 or slots < 1:
        return {"error": "narx musbat, kunlar va joylar kamida 1 bolishi kerak"}

    tours_used = (await db.execute(select(func.count(Tour.id)).where(Tour.company_id == cid))).scalar() or 0
    if not within_tour_limit(
        (await db.execute(select(Company.tariff).where(Company.id == cid))).scalar_one_or_none(),
        tours_used,
    ):
        return {"error": "Tarif boyicha turlar limiti tugagan — yuqori tarifga oting"}

    start_date: Optional[date] = None
    raw_date = args.get("start_date")
    if raw_date:
        try:
            start_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            return {"error": "sana formati notogri, YYYY-MM-DD kutiladi"}

    booking_type = args.get("booking_type") if args.get("booking_type") in ("group", "individual") else "group"
    country = str(args.get("country") or "Uzbekistan")
    city = str(args["city"])
    title = str(args["title"])
    description = str(args.get("description") or f"{title} — {city}, {country}. {duration} kunlik tur.")

    tour = Tour(
        company_id=cid, title=title, description=description, city=city, country=country,
        price=price, currency=str(args.get("currency") or "UZS"), duration_days=duration,
        available_slots=slots, booking_type=booking_type, start_date=start_date, is_active=True,
    )
    db.add(tour)
    await db.commit()
    await db.refresh(tour)
    return {"ok": True, "tur_id": tour.id, "nom": tour.title, "_amal": f"Tur qoshildi: {tour.title}"}


async def _t_update_tour_price(db: AsyncSession, cid: int, args: dict) -> dict:
    try:
        tour_id = int(args["tour_id"])
        price = float(args["price"])
    except (KeyError, TypeError, ValueError):
        return {"error": "tour_id va price kerak (son)"}
    if price <= 0:
        return {"error": "narx musbat bolishi kerak"}
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id, Tour.company_id == cid))).scalar_one_or_none()
    if not tour:
        return {"error": "Bunday tur topilmadi"}
    old = tour.price
    tour.price = price
    await db.commit()
    return {"ok": True, "tur": tour.title, "eski_narx": old, "yangi_narx": price,
            "_amal": f"{tour.title} narxi {old:.0f} -> {price:.0f}"}


async def _t_set_tour_active(db: AsyncSession, cid: int, args: dict) -> dict:
    try:
        tour_id = int(args["tour_id"])
    except (KeyError, TypeError, ValueError):
        return {"error": "tour_id kerak"}
    is_active = bool(args.get("is_active", True))
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id, Tour.company_id == cid))).scalar_one_or_none()
    if not tour:
        return {"error": "Bunday tur topilmadi"}
    tour.is_active = is_active
    await db.commit()
    return {"ok": True, "tur": tour.title, "faol": is_active,
            "_amal": f"{tour.title} {'faollashtirildi' if is_active else 'nofaol qilindi'}"}


# Tool nomi -> (handler, yozuvchi amalmi). Yozuvchilar "amallar" royxatiga tushadi.
_TOOLS = {
    "get_report": (_t_get_report, False),
    "count_tours": (_t_count_tours, False),
    "list_tours": (_t_list_tours, False),
    "recent_bookings": (_t_recent_bookings, False),
    "count_customers": (_t_count_customers, False),
    "get_plan": (_t_get_plan, False),
    "create_tour": (_t_create_tour, True),
    "update_tour_price": (_t_update_tour_price, True),
    "set_tour_active": (_t_set_tour_active, True),
}


_SYSTEM = """Sen "{company}" tur firmasining shaxsiy AI yordamchisisan. Sen FAQAT
shu firmaning malumotini korasan va oʻzgartirasan.

Har javobingda ANIQ bitta JSON obyekt qaytar, boshqa matnsiz. Ikki xil boladi:
1) Tool chaqirish:  {{"tool": "nom", "args": {{...}}}}
2) Foydalanuvchiga javob:  {{"reply": "matn"}}

Mavjud toollar:
- get_report(range: "24h"|"7d"|"28d"|"1y"|"all") — tashrif, mijoz, bron, daromad, DAU/MAU, top turlar
- count_tours(active_only?: bool) — turlar soni
- list_tours(limit?: int, active_only?: bool) — turlar royxati (id bilan)
- recent_bookings(limit?: int) — oxirgi bronlar
- count_customers() — mijozlar soni
- get_plan() — tarif va limitlar
- create_tour(title, city, price, duration_days, available_slots, country?, booking_type?, start_date?, description?) — yangi tur qoshadi
- update_tour_price(tour_id, price) — mavjud tur narxini oʻzgartiradi
- set_tour_active(tour_id, is_active) — turni faol/nofaol qiladi

Qoidalar:
- Malumot kerak bolsa tool chaqir, oʻzingdan raqam toʻqima.
- create_tour uchun majburiy: title, city, price, duration_days, available_slots.
  Biror maydon yetishmasa, toolni chaqirma — {{"reply": "..."}} bilan yetishmayotganini SORA.
- Tur qoshish yoki oʻzgartirishdan (create_tour, update_tour_price, set_tour_active)
  OLDIN foydalanuvchiga qisqa xulosani koʻrsatib tasdiq sora. Foydalanuvchi "ha"
  degandan keyingina toolni chaqir.
- Turni id boʻyicha oʻzgartirasan — id ni bilmasang avval list_tours chaqir.
- Xisobot soʻralganda faqat raqamni aytma: qisqa tahlil qil va yetishmovchiliklarni
  ayt (masalan kam faol tur, past daromad, oz bron), 1-2 amaliy maslahat ber.
- Qisqa va aniq yoz. Ozbek tilida, tutuq belgisisiz (yoq, boladi, oʻzgartirish emas).
- Ochirish imkoni yoʻq."""


async def _call_gemini(contents: list[dict], system: str) -> str:
    settings = get_settings()
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3},
    }
    url = _ENDPOINT.format(model=settings.gemini_model)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, params={"key": settings.gemini_api_key}, json=payload)
    if resp.status_code != 200:
        logger.warning("Gemini assistant xatosi %s: %s", resp.status_code, resp.text[:300])
        if resp.status_code == 429:
            raise AssistantUnavailable("Kunlik tekin limit tugadi, keyinroq urining")
        raise AssistantUnavailable(f"AI xizmati javob bermadi ({resp.status_code})")
    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise AssistantUnavailable("AI javobi kutilgan formatda emas") from exc


def _parse(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return {"reply": raw}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {"reply": raw}


async def run_assistant(
    db: AsyncSession, user: User, message: str, history: list[dict]
) -> dict:
    """Suhbatni bir qadam oldinga suradi. {reply, actions} qaytaradi."""
    if not is_configured():
        raise AssistantUnavailable("AI sozlanmagan — GEMINI_API_KEY qoshing")
    cid = user.company_id
    if not cid:
        raise AssistantUnavailable("Kompaniyaga biriktirilmagansiz")

    company = (await db.execute(select(Company).where(Company.id == cid))).scalar_one_or_none()
    system = _SYSTEM.format(company=company.name if company else "firma")

    contents: list[dict] = []
    for m in history[-12:]:
        role = "model" if m.get("role") in ("assistant", "model") else "user"
        text = str(m.get("content", "")).strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    actions: list[str] = []
    for _ in range(_MAX_STEPS):
        raw = await _call_gemini(contents, system)
        data = _parse(raw)

        tool = data.get("tool")
        if not tool:
            return {"reply": str(data.get("reply") or raw), "actions": actions}

        handler_pair = _TOOLS.get(tool)
        if not handler_pair:
            result = {"error": f"Nomalum tool: {tool}"}
            is_write = False
        else:
            handler, is_write = handler_pair
            try:
                result = await handler(db, cid, data.get("args") or {})
            except Exception:  # noqa: BLE001 — tool xatosi suhbatni buzmasin
                logger.exception("Assistant tool xatosi: %s", tool)
                await db.rollback()
                result = {"error": "Tool bajarilmadi"}

        if is_write and isinstance(result, dict) and result.get("_amal"):
            actions.append(result.pop("_amal"))

        contents.append({"role": "model", "parts": [{"text": raw}]})
        contents.append({
            "role": "user",
            "parts": [{"text": f"TOOL_NATIJA({tool}): {json.dumps(result, ensure_ascii=False)}"}],
        })

    # Sikl tugadi — modelni yakuniy javobga majburlaymiz.
    contents.append({
        "role": "user",
        "parts": [{"text": "Endi foydalanuvchiga qisqa yakuniy javob ber: {\"reply\": \"...\"}"}],
    })
    raw = await _call_gemini(contents, system)
    data = _parse(raw)
    return {"reply": str(data.get("reply") or raw), "actions": actions}
