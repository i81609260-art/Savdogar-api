"""Rasm ko'rinishidagi price-list'ni matnga o'girish.

Operatorlar narxni ko'pincha **afisha** qilib tashlaydi: chiroyli fon,
logotip, ustiga yozilgan narxlar. Excel yoki PDF emas — rasm. Bunday
price-list'ni o'qish uchun matnni rasmdan ajratib olish kerak.

Nima uchun bu alohida modulda
-----------------------------
Qolgan hamma tahlil (Excel, CSV, matn, PDF) **tashqi xizmatsiz** ishlaydi.
Rasm — yagona istisno: mahalliy vositalar bilan afishadagi bezakli matnni
ishonchli o'qib bo'lmaydi.

Shuning uchun bu qism **ixtiyoriy**: `GEMINI_API_KEY` bo'lsa ishlaydi
(loyihada allaqachon bor va qo'ng'iroq tahlilida ishlatilyapti), bo'lmasa
tushunarli xabar qaytadi va ilova ishlashda davom etadi. Boshqa hech bir
imkoniyat bunga bog'liq emas.

Natija baribir bir xil yo'ldan o'tadi: rasm -> matn -> `parse_text()`.
Ya'ni yo'nalish, ovqat, yulduz, narx aniqlash qoidalari o'zgarmaydi.
"""

from __future__ import annotations

import base64
import logging

import httpx

from app.config import get_settings
from app.services.pricelist_parser import PricelistResult, parse_text

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Afisha odatda kichik bo'ladi; katta fayl ham xarajat, ham kechikish.
MAX_IMAGE_BYTES = 8 * 1024 * 1024

SUPPORTED_MIME = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic",
}

# Modeldan STRUKTURA emas, faqat MATN so'raladi. Sabab: tahlil qoidalari
# (yo'nalish, ovqat, yulduz, narx) allaqachon `tour_taxonomy` da va ular
# testlar bilan qoplangan. Modelga strukturani ham topshirsak, natija
# oldindan aytib bo'lmaydigan bo'lib qolardi va ikkita tahlil mantiqi
# paydo bo'lardi.
_PROMPT = """Bu tur operatorning narxlar ro'yxati (price-list) rasmi.

Rasmdagi BARCHA matnni o'qib, o'zgartirmasdan qaytar. Qoidalar:

1. Har mehmonxona alohida satrda bo'lsin.
2. Sarlavha satrlarini (yo'nalish, sana, kecha soni) saqlab qol — ular
   keyingi satrlarga tegishli.
3. Narx, yulduz (5*), ovqat kodi (AI, UAI, HB, BB, FB) o'zgartirilmasin.
4. Hech narsa qo'shma, izohlama, tarjima qilma.
5. Faqat matn qaytar — JSON emas, markdown emas.

Agar rasmda narxlar ro'yxati bo'lmasa, bo'sh javob qaytar."""


class ImageOcrUnavailable(RuntimeError):
    """Rasmni o'qib bo'lmadi — sozlanmagan yoki xizmat javob bermadi."""


def is_configured() -> bool:
    """Rasm tahlili yoqilganmi?"""
    return bool(get_settings().gemini_api_key)


async def image_to_text(content: bytes, mime_type: str) -> str:
    """Rasmdagi matnni ajratib oladi."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ImageOcrUnavailable(
            "Rasmli price-list uchun GEMINI_API_KEY sozlanmagan. "
            "Excel, CSV, PDF yoki matn yuboring."
        )

    mime = (mime_type or "").split(";")[0].strip().lower()
    if mime not in SUPPORTED_MIME:
        raise ImageOcrUnavailable(f"Rasm formati qo'llab-quvvatlanmaydi: {mime}")

    if len(content) > MAX_IMAGE_BYTES:
        raise ImageOcrUnavailable(
            f"Rasm juda katta ({len(content) // 1024 // 1024} MB), "
            f"{MAX_IMAGE_BYTES // 1024 // 1024} MB gacha bo'lishi kerak"
        )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": base64.b64encode(content).decode(),
                        }
                    },
                ]
            }
        ],
        # Past temperatura — bu ijodiy vazifa emas, nusxa ko'chirish.
        "generationConfig": {"temperature": 0.0},
    }

    url = _ENDPOINT.format(model=settings.gemini_model)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url, params={"key": settings.gemini_api_key}, json=payload
            )
    except httpx.HTTPError as exc:
        raise ImageOcrUnavailable(f"Xizmatga ulanib bo'lmadi: {exc}") from exc

    if response.status_code != 200:
        logger.warning(
            "Rasm tahlili xatosi %s: %s", response.status_code, response.text[:300]
        )
        if response.status_code == 429:
            raise ImageOcrUnavailable("Kunlik limit tugadi, ertaga qayta urining")
        raise ImageOcrUnavailable(f"Xizmat javob bermadi ({response.status_code})")

    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError) as exc:
        raise ImageOcrUnavailable("Javob kutilgan formatda emas") from exc


async def parse_image(content: bytes, mime_type: str) -> PricelistResult:
    """Rasmni tahlil qilib takliflar qaytaradi.

    Istisno tashlamaydi — qolgan tahlil yo'llari bilan bir xil shaklda
    `PricelistResult` qaytaradi, sabab `warnings` ichida bo'ladi. Shunda
    chaqiruvchi (yuklash endpointi, Telegram bot) ikki xil xato ishlovini
    yozishi shart emas.
    """
    try:
        text = await image_to_text(content, mime_type)
    except ImageOcrUnavailable as exc:
        return PricelistResult(offers=[], warnings=[str(exc)])

    if not (text or "").strip():
        return PricelistResult(
            offers=[], warnings=["Rasmda narxlar ro'yxati topilmadi"]
        )

    # Rasmdan chiqqan matn odatdagi matnli price-list bilan BIR XIL yo'ldan
    # o'tadi — tahlil qoidalari ikkiga bo'linmasin.
    result = parse_text(text)
    if not result.offers:
        result.warnings.append("Rasm o'qildi, lekin narx topilmadi")
    return result
