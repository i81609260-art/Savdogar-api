"""Valyuta kurslari — O'zbekiston Markaziy banki.

Nega kerak: `tours.price` oddiy son, valyuta esa alohida ustunda. Ular
o'rtasida kurs bo'lmagani uchun `ORDER BY price` turli valyutalarni
solishtira olmasdi — 10 001 EUR (≈137 mln so'm) 12 mln so'mlik turdan
"arzonroq" bo'lib chiqardi. `min_price`/`max_price` filtrlari ham xuddi
shu nuqsonga ega edi.

Yechim: har bir tur uchun so'mdagi qiymat (`price_uzs`) hisoblanadi va
saralash/filtr o'shani ishlatadi. Ko'rsatishda asl valyuta qoladi.

Ishonchlilik qoidasi: kurs olinmasa ham tur SAQLANISHI kerak. Tashqi
xizmatning uzilishi mahsulotning asosiy amalini to'xtatib qo'ymasligi
lozim, shuning uchun uch bosqichli zaxira bor — kesh, so'ngra oxirgi
ma'lum qiymat, so'ngra qat'iy zaxira.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

# Kurs kuniga bir marta yangilanadi, shuning uchun 6 soat yetarli va
# ortiqcha so'rov qilinmaydi.
_TTL_SECONDS = 6 * 60 * 60

# Kunlik halqaning kutish oralig'i. Alohida doimiy — sinovda uni
# almashtirish `asyncio.sleep` ni yamoqlashdan xavfsizroq: u global
# modul va yamoqlansa sinovning o'zi ham ta'sirlanardi.
_DAILY_SLEEP_SECONDS = 24 * 60 * 60

# Oxirgi chora. FAQAT MB ham, kesh ham ishlamaganda qo'llanadi (masalan
# server yangi ko'tarilgan va tarmoq yo'q). Aniq bo'lishi shart emas —
# vazifasi tur saqlanishini to'xtatib qo'ymaslik. Sana: 2026-08.
_FALLBACK: dict[str, float] = {
    "UZS": 1.0,
    "USD": 11_900.0,
    "EUR": 13_750.0,
    "RUB": 146.0,
}

_cache: dict[str, float] = {}
_fetched_at: float = 0.0
_lock = asyncio.Lock()


def _parse(rows: list[dict]) -> dict[str, float]:
    """MB javobidan {valyuta: so'mdagi_qiymat} yasaydi.

    `Nominal` E'TIBORGA OLINADI: ba'zi valyutalar 10 yoki 100 birlik uchun
    kotirovka qilinadi (masalan yapon iyenasi). Uni hisobga olmasak,
    qiymat 100 barobar xato bo'lardi.
    """
    rates: dict[str, float] = {"UZS": 1.0}
    for row in rows:
        code = (row.get("Ccy") or "").upper()
        if not code:
            continue
        try:
            rate = float(row["Rate"])
            nominal = float(row.get("Nominal") or 1) or 1.0
        except (KeyError, TypeError, ValueError):
            continue
        if rate > 0:
            rates[code] = rate / nominal
    return rates


async def refresh_rates(force: bool = False) -> dict[str, float]:
    """Kurslarni oladi. Keshi yangi bo'lsa tarmoqqa chiqmaydi."""
    global _fetched_at

    fresh = _cache and (time.time() - _fetched_at) < _TTL_SECONDS
    if fresh and not force:
        return _cache

    async with _lock:
        # Kutayotganda boshqa so'rov yangilagan bo'lishi mumkin.
        if _cache and (time.time() - _fetched_at) < _TTL_SECONDS and not force:
            return _cache
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(CBU_URL)
                response.raise_for_status()
                rates = _parse(response.json())
            if len(rates) > 1:
                _cache.clear()
                _cache.update(rates)
                _fetched_at = time.time()
                log.info("Valyuta kurslari yangilandi: %s ta", len(rates))
        except Exception as exc:  # noqa: BLE001
            # Eski kesh ESKIRGAN bo'lsa ham yangi so'rovdan yaxshiroq —
            # kurs kuniga bir marta o'zgaradi, uzilish esa vaqtinchalik.
            log.warning("MB kurslari olinmadi (%s) — eski qiymatlar ishlatiladi", exc)

    return _cache or _FALLBACK


async def daily_refresh_loop(recompute) -> None:
    """Har kuni kursni yangilab, turlarning so'mdagi narxini qayta hisoblaydi.

    `price_uzs` tur SAQLANGANDA hisoblanadi va keyin qotib qoladi. Kurs
    o'zgarsa u eskiradi: 10-15% siljish saralash tartibini sezilarli
    buzadi. Shuning uchun kuniga bir marta qayta hisoblanadi.

    Alohida cron xizmati EMAS, ilova ichidagi vazifa: Railway'da alohida
    rejalashtiruvchi qo'shish uchun yana bitta xizmat va uning sozlamasi
    kerak bo'lardi, bu esa bitta amal uchun ortiqcha.

    Xato bo'lsa halqa TO'XTAMAYDI — bir kunlik uzilish tufayli keyingi
    kunlar ham yangilanmay qolishi eng yomon natija bo'lardi.
    """
    while True:
        try:
            await refresh_rates(force=True)
            await recompute()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Kunlik kurs yangilash xatosi: %s", exc)
        await asyncio.sleep(_DAILY_SLEEP_SECONDS)


def rate_for(currency: Optional[str]) -> float:
    """Bir birlik valyutaning so'mdagi qiymati (keshdan, tarmoqsiz)."""
    code = (currency or "UZS").upper()
    return _cache.get(code) or _FALLBACK.get(code) or 1.0


def to_uzs(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    """Narxni so'mga o'giradi. Saralash va filtr uchun.

    Tarmoqqa CHIQMAYDI — keshdagi qiymatdan foydalanadi. Shu tufayli tur
    saqlash amali tashqi xizmatga bog'liq bo'lib qolmaydi.
    """
    if amount is None:
        return None
    return round(float(amount) * rate_for(currency), 2)
