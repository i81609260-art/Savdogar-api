"""Firma botining qo'shimcha buyruqlari: ID, sayt ma'lumoti, hisobot.

Uchta buyruq, uchta xil ruxsat darajasi — bu farq muhim:

* `/id`      — hammaga ochiq. Foydalanuvchi O'Z ID sini ko'radi, bu uning
               shaxsiy ma'lumoti va bildirishnomalarni sozlash uchun kerak.
* `/sayt`    — hammaga ochiq. Firmaning ommaviy ma'lumoti, saytda ham bor.
* `/hisobot` — FAQAT xodimga. Ichida daromad, bronlar, mijozlar soni bor.
               Mijoz buni ko'rmasligi kerak.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.branch import Branch
from app.models.company import Company
from app.models.tour import Tour
from app.models.user import User
from app.services.telegram_staff import find_staff

log = logging.getLogger(__name__)

# Telegram xabari 4096 belgidan oshmasin.
MAX_MESSAGE = 3800


def _clip(text: str, limit: int = MAX_MESSAGE) -> str:
    return text if len(text) <= limit else text[: limit - 20] + "\n\n… (qisqartirildi)"


def _money(value: float | None, currency: str = "so'm") -> str:
    if not value:
        return f"0 {currency}"
    return f"{value:,.0f} {currency}".replace(",", " ")


# --------------------------------------------------------------------------
# /id — Telegram ID
# --------------------------------------------------------------------------
def build_id_reply(message: dict) -> str:
    """Foydalanuvchining Telegram ID sini va uni nimaga ishlatishini beradi.

    Telegram ID ni topish — sozlashdagi eng ko'p uchraydigan to'siq: uni
    ilovaning o'zida ko'rsatmaydi va odam uchinchi tomon botlarini qidirib
    ketadi. Shuning uchun bot uni o'zi aytadi va nima uchun kerakligini
    tushuntiradi.
    """
    chat = message.get("chat") or {}
    sender = message.get("from") or {}

    chat_id = chat.get("id")
    user_id = sender.get("id")
    username = sender.get("username")
    full_name = " ".join(
        p for p in (sender.get("first_name"), sender.get("last_name")) if p
    )

    lines = ["🆔 <b>Sizning Telegram ma'lumotlaringiz</b>", ""]
    if full_name:
        lines.append(f"👤 Ism: {full_name}")
    if username:
        lines.append(f"🔖 Username: @{username}")
    lines.append(f"🆔 User ID: <code>{user_id}</code>")

    # Guruhda chat ID user ID dan farq qiladi — bildirishnoma guruhga
    # kelishi kerak bo'lsa aynan shu kerak bo'ladi.
    if chat_id != user_id:
        chat_type = chat.get("type", "chat")
        lines.append(f"💬 Chat ID ({chat_type}): <code>{chat_id}</code>")

    lines += [
        "",
        "<b>Bu nimaga kerak?</b>",
        "Savdogar panelida bildirishnoma sozlashda shu ID so'raladi — "
        "yangi bron yoki so'rov kelganda xabar aynan shu chatga tushadi.",
        "",
        "<b>Qanday ishlatiladi:</b>",
        "1. Yuqoridagi ID raqamini nusxalang (ustiga bosing)",
        "2. Panel → <b>Integratsiyalar</b> → <b>Telegram</b>",
        "3. «Chat ID» maydoniga qo'ying va saqlang",
        "",
        "ℹ️ Guruhga xabar kelishi kerak bo'lsa: botni guruhga qo'shing va "
        "o'sha yerda <code>/id</code> yozing — guruhning Chat ID si chiqadi "
        "(u minus bilan boshlanadi).",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Sayt ma'lumotlari — matn ko'rinishida
# --------------------------------------------------------------------------
async def build_site_reply(
    db: AsyncSession, company: Company, site_url: str
) -> str:
    """Firma ma'lumotini matnda beradi.

    Ilgari bot faqat havola yuborardi. Havola bosish — brauzer ochish,
    kutish; ko'p foydalanuvchi buni qilmaydi. Asosiy ma'lumot Telegram'ning
    o'zida ko'rinishi kerak, havola esa qo'shimcha bo'lsin.
    """
    lines = [f"🏢 <b>{company.name}</b>", ""]

    if company.description:
        lines += [_clip(company.description.strip(), 700), ""]

    # DIQQAT: `Company` da `address` maydoni yo'q — manzil `branches`
    # jadvalida, filial darajasida saqlanadi. Shu yerda `company.address`
    # o'qilsa AttributeError chiqadi.
    contacts = []
    if company.city:
        contacts.append(f"📍 {company.city}")
    if company.phone:
        contacts.append(f"📞 <a href='tel:{company.phone}'>{company.phone}</a>")
    if company.email:
        contacts.append(f"📧 {company.email}")
    # Manzil firma darajasida emas, filialda saqlanadi. Bosh ofisniki
    # foydalanuvchiga eng kerakli — uni ham qo'shamiz.
    main_branch = (
        await db.execute(
            select(Branch)
            .where(Branch.company_id == company.id)
            .order_by(Branch.is_main.desc(), Branch.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if main_branch and main_branch.address:
        contacts.append(f"🏠 {main_branch.address}")

    if contacts:
        lines += contacts + [""]

    # Faol turlar soni — "bu firma ishlayaptimi" degan savolga javob.
    active_tours = (
        await db.execute(
            select(func.count(Tour.id)).where(
                Tour.company_id == company.id, Tour.is_active.is_(True)
            )
        )
    ).scalar() or 0
    if active_tours:
        lines += [f"🗺 Faol turlar: <b>{active_tours}</b> ta", ""]

    # `company_info` — admin panelda erkin matn sifatida to'ldiriladi
    # (saytda ham, Tella uchun ham shu ishlatiladi).
    if company.company_info and company.company_info.strip():
        lines += ["ℹ️ <b>Qo'shimcha</b>", _clip(company.company_info.strip(), 1200), ""]

    lines.append(f"🌐 {site_url}")
    return _clip("\n".join(lines))


# --------------------------------------------------------------------------
# /hisobot — FAQAT xodimga
# --------------------------------------------------------------------------
async def build_report_reply(
    db: AsyncSession, company_id: int, chat_id: str | int
) -> Optional[str]:
    """To'liq firma hisoboti.

    `None` qaytarsa — so'rovchi xodim emas va hisobot ko'rsatilmasin.
    Ichida daromad va mijozlar soni bor; mijoz buni ko'rmasligi kerak.
    """
    staff = await find_staff(db, company_id, chat_id)
    if staff is None:
        return None

    tours_total = (
        await db.execute(
            select(func.count(Tour.id)).where(Tour.company_id == company_id)
        )
    ).scalar() or 0
    tours_active = (
        await db.execute(
            select(func.count(Tour.id)).where(
                Tour.company_id == company_id, Tour.is_active.is_(True)
            )
        )
    ).scalar() or 0

    # Bronlar holati bo'yicha — bitta so'rovda.
    # `Booking.company_id` bevosita bor, shuning uchun `Tour` orqali JOIN
    # qilish shart emas: tezroq, va turi o'chirilgan bron ham hisobga
    # tushadi (JOIN bo'lsa u yo'qolib qolardi).
    status_rows = (
        await db.execute(
            select(Booking.status, func.count(Booking.id), func.sum(Booking.total_price))
            .where(Booking.company_id == company_id)
            .group_by(Booking.status)
        )
    ).all()

    by_status = {row[0]: (row[1] or 0, float(row[2] or 0)) for row in status_rows}
    bookings_total = sum(count for count, _ in by_status.values())
    confirmed_count, confirmed_sum = by_status.get(BookingStatus.CONFIRMED, (0, 0.0))
    pending_count, _ = by_status.get(BookingStatus.PENDING, (0, 0.0))

    lines = [
        "📊 <b>Firma hisoboti</b>",
        "",
        "🗺 <b>Turlar</b>",
        f"   Jami: {tours_total} ta",
        f"   Faol: {tours_active} ta",
        "",
        "📅 <b>Bronlar</b>",
        f"   Jami: {bookings_total} ta",
        f"   Tasdiqlangan: {confirmed_count} ta",
        f"   Kutilmoqda: {pending_count} ta",
        "",
        "💰 <b>Daromad</b> (tasdiqlangan bronlar)",
        f"   {_money(confirmed_sum)}",
    ]

    # Eng ko'p bron qilingan turlar.
    top = (
        await db.execute(
            select(Tour.title, func.count(Booking.id))
            .join(Booking, Booking.tour_id == Tour.id)
            .where(Booking.company_id == company_id)
            .group_by(Tour.id, Tour.title)
            .order_by(func.count(Booking.id).desc())
            .limit(5)
        )
    ).all()
    if top:
        lines += ["", "🔝 <b>Ommabop turlar</b>"]
        for index, (title, count) in enumerate(top, 1):
            lines.append(f"   {index}. {title} — {count} bron")

    lines += ["", f"👤 {staff.full_name}", "Batafsil: panel → <b>Hisobotlar</b>"]
    return _clip("\n".join(lines))


# --------------------------------------------------------------------------
# Umumiy dispetcher
# --------------------------------------------------------------------------
async def try_handle_command(
    db: AsyncSession, company_id: int, company: Company, message: dict, site_url: str
) -> Optional[str]:
    """Qo'shimcha buyruqlarni qayta ishlaydi.

    `None` qaytarsa bot odatdagi oqimida davom etadi.
    """
    text = (message.get("text") or "").strip().lower()
    if not text:
        return None

    if text in ("/id", "🆔 id", "/myid", "id"):
        return build_id_reply(message)

    if text in ("/hisobot", "📊 hisobot", "/report"):
        chat_id = (message.get("chat") or {}).get("id")
        reply = await build_report_reply(db, company_id, chat_id)
        if reply is None:
            # Mijozga hisobot borligini ham bildirmaymiz — shunchaki
            # bog'lanish yo'riqnomasi.
            return (
                "🔒 Bu buyruq firma xodimlari uchun.\n\n"
                "Xodim bo'lsangiz hisobingizni bog'lang:\n"
                "<code>/link email parol</code>"
            )
        return reply

    if text in ("/malumot", "/info", "ℹ️ malumot"):
        return await build_site_reply(db, company, site_url)

    return None
