"""Telegram orqali price-list qabul qilish.

Operatorlar narxni Telegram'ga tashlaydi. Agent o'sha xabarni firma botiga
**forward** qiladi — narxlar avtomatik bazaga tushadi. Panelga kirib fayl
tashlashdan ko'ra tez: bir bosish.

XAVFSIZLIK — bu modulning asosiy mas'uliyati
--------------------------------------------
Firma boti **mijozlar** bilan ishlaydi: ular tur ko'radi va bron qiladi.
Agar price-list'ni istalgan yozgan odamdan qabul qilsak, har qanday mijoz
soxta narx yuborib firmaning narx bazasini buza olardi — va agent o'sha
soxta narx bo'yicha mijozga taklif berardi.

Shuning uchun price-list FAQAT tanilgan xodimdan qabul qilinadi:
`users.telegram_chat_id` shu chat'ga bog'langan va foydalanuvchi AYNAN shu
firmaning ADMIN yoki OPERATOR i bo'lishi shart. Boshqa hamma uchun bu modul
`None` qaytaradi va bot odatdagi mijoz oqimida davom etadi.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tour_offer import OfferSource
from app.services.offer_service import save_offers
from app.services.pricelist_parser import (
    IMAGE_EXT,
    parse_pricelist_async,
    parse_text,
)

# Xodim tekshiruvi umumiy modulda — hisobotlar ham AYNAN shu qoidadan
# foydalanadi. Ikki joyda takrorlansa vaqt o'tib biri o'zgarib qolardi.
from app.services.telegram_staff import find_staff, link_staff

__all__ = ["try_handle_pricelist", "find_staff", "link_staff", "MIN_TEXT_LEN"]

log = logging.getLogger(__name__)

TELEGRAM_FILE_URL = "https://api.telegram.org/file/bot{token}/{path}"
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

# Telegram hujjat cheklovi bilan bir xil tartibda. Price-list amalda
# bundan katta bo'lmaydi.
MAX_FILE_BYTES = 10 * 1024 * 1024

# Bundan qisqa matn price-list emas — oddiy savol yoki salomlashish.
MIN_TEXT_LEN = 40

SUPPORTED_EXT = (".xlsx", ".xlsm", ".csv", ".pdf", ".txt")


async def _api(token: str, method: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            TELEGRAM_API.format(token=token, method=method), json=kwargs
        )
        return response.json()


async def _download(token: str, file_id: str) -> Optional[bytes]:
    """Telegram'dan faylni yuklab oladi."""
    info = await _api(token, "getFile", file_id=file_id)
    path = (info.get("result") or {}).get("file_path")
    if not path:
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(TELEGRAM_FILE_URL.format(token=token, path=path))
        if response.status_code != 200:
            return None
        content = response.content
        return content if len(content) <= MAX_FILE_BYTES else None


def _largest_photo(message: dict) -> Optional[dict]:
    """Telegram rasmni bir necha o'lchamda yuboradi — eng kattasi kerak.

    Kichik nusxada matn o'qib bo'lmaydi. Ro'yxat odatda o'sish tartibida
    keladi, lekin bunga tayanmasdan aniq eng kattasini tanlaymiz.
    """
    photos = message.get("photo") or []
    if not photos:
        return None
    return max(photos, key=lambda p: (p.get("file_size") or 0, p.get("width") or 0))


def _summary(found: int, saved: int, skipped: int, warnings: list[str]) -> str:
    if not saved:
        detail = warnings[0] if warnings else "narx topilmadi"
        return f"⚠️ Price-list o'qilmadi — {detail}"

    lines = [f"✅ <b>{saved}</b> ta taklif qo'shildi"]
    if skipped:
        # Jim yutilgan qator — yo'qolgan narx. Agent bilishi kerak.
        lines.append(f"⚠️ {skipped} qator o'qilmadi (mehmonxona yoki narx yo'q)")
    for warning in warnings[:2]:
        lines.append(f"ℹ️ {warning}")
    lines.append("\nNarxlar panelda: <b>Narxlar</b> bo'limi")
    return "\n".join(lines)


async def try_handle_pricelist(
    db: AsyncSession,
    token: str,
    company_id: int,
    message: dict,
) -> Optional[str]:
    """Xabarni price-list sifatida qayta ishlashga urinadi.

    Qaytaradi:
      * matn — xabar qayta ishlandi, bot shuni javob qilsin;
      * `None` — bu price-list emas, bot odatdagi mijoz oqimida davom etsin.
    """
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None:
        return None

    text = (message.get("text") or message.get("caption") or "").strip()

    # `/link` — bog'lanish. Boshqa hamma narsa xodimlik talab qiladi.
    if text.startswith("/link"):
        return await link_staff(db, company_id, chat_id, text)

    document = message.get("document")
    looks_like_pricelist = (
        bool(document) or bool(message.get("photo")) or len(text) >= MIN_TEXT_LEN
    )
    if not looks_like_pricelist:
        return None

    staff = await find_staff(db, company_id, chat_id)
    if staff is None:
        # Mijoz yozgan — aralashmaymiz, odatdagi oqim davom etsin.
        return None

    # ---- Hujjat yoki rasm ----
    photo = _largest_photo(message)
    if document or photo:
        filename = (document or {}).get("file_name", "").lower()
        # DIQQAT: standart qiymat BO'SH bo'lishi shart. Ilgari bu yerda
        # "image/jpeg" turardi va mime'siz HAR QANDAY hujjat (masalan
        # .docx) rasm deb belgilanib, format tekshiruvidan o'tib ketardi.
        mime = (document or {}).get("mime_type") or ""

        # Rasm ikki xil kelishi mumkin: `photo` (Telegram siqib yuboradi)
        # yoki `document` (fayl sifatida yuborilgan rasm).
        is_image = bool(photo) or filename.endswith(IMAGE_EXT) or "image" in mime
        if not is_image and not filename.endswith(SUPPORTED_EXT):
            return (
                "⚠️ Bu format qo'llab-quvvatlanmaydi.\n"
                "Excel (.xlsx), CSV, PDF, rasm yoki matn yuboring."
            )

        source = document or photo
        if (source.get("file_size") or 0) > MAX_FILE_BYTES:
            return "⚠️ Fayl juda katta (eng ko'pi 10 MB)."

        content = await _download(token, source["file_id"])
        if content is None:
            return "⚠️ Faylni yuklab bo'lmadi, qayta urinib ko'ring."

        result = await parse_pricelist_async(
            content,
            filename=filename or ("afisha.jpg" if photo else ""),
            content_type=mime if not photo else "image/jpeg",
        )
    else:
        # ---- Matn (forward qilingan xabar) ----
        result = parse_text(text)
        if not result.offers:
            # Uzun matn har doim ham price-list emas — xodim oddiy savol
            # yozgan bo'lishi mumkin. Jim o'tkazamiz.
            return None

    saved = await save_offers(
        db,
        company_id=company_id,
        offers=result.offers,
        source=OfferSource.PRICELIST,
    )
    log.info(
        "Telegram price-list: firma=%s xodim=%s qo'shildi=%s",
        company_id, staff.id, len(saved),
    )
    return _summary(len(result.offers), len(saved), result.skipped, result.warnings)
