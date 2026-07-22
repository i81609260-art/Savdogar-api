"""Platforma egasiga Telegram orqali muhim hodisalar haqida xabar.

Kompaniya botlaridan (`telegram_service.py`) farqi: bu yerdagi xabarlar
mijozlarga emas, platforma superadminiga boradi — hozircha tarif o'zgarishi.

Xabar yuborilmasligi asosiy amalni hech qachon to'xtatmasligi kerak, shuning
uchun barcha xatolar yutiladi va faqat logga yoziladi.
"""

from __future__ import annotations

import html
import logging
from typing import Optional

import httpx

from app.config import get_settings
from app.models.company import Company
from app.models.user import User
from app.services.tariff import get_tariff

logger = logging.getLogger(__name__)
settings = get_settings()

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _admin_chat_ids() -> list[str]:
    """Xabar boradigan chat ID lar (vergul bilan ajratilgan ro'yxatdan)."""
    return [c.strip() for c in settings.telegram_admin_chat_ids.split(",") if c.strip()]


def enabled() -> bool:
    """Bot tokeni ham, kamida bitta chat ID ham sozlanganmi."""
    return bool(settings.telegram_bot_token) and bool(_admin_chat_ids())


def _money(amount: int | float | None) -> str:
    """199990 -> "199 990" (mingliklar orasida bo'sh joy)."""
    if not amount:
        return "—"
    return f"{int(amount):,}".replace(",", " ")


async def _send(chat_id: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            _TELEGRAM_API.format(token=settings.telegram_bot_token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        )
        response.raise_for_status()


async def notify_tariff_change(
    company: Company,
    old_tariff: str,
    new_tariff: str,
    actor: Optional[User] = None,
) -> None:
    """Tur firma tarifni o'zgartirganda superadminga xabar yuboradi.

    `actor` — o'zgartirgan foydalanuvchi (bo'lmasa ko'rsatilmaydi).
    """
    if not enabled():
        return

    old_plan = get_tariff(old_tariff)
    new_plan = get_tariff(new_tariff)
    # Ko'tarilish yoki tushish — bir qarashda ko'rinib tursin.
    arrow = "⬆️" if new_plan.get("order", 0) > old_plan.get("order", 0) else "⬇️"

    lines = [
        f"{arrow} <b>Tarif ozgardi</b>",
        "",
        f"🏢 <b>{html.escape(company.name)}</b>",
        f"📊 {html.escape(old_plan['name'])} → <b>{html.escape(new_plan['name'])}</b>",
        f"💰 {_money(new_plan.get('price'))} som/oy",
    ]
    if actor:
        lines.append(f"👤 {html.escape(actor.full_name)} ({html.escape(actor.email)})")
    if company.id:
        lines.append(f"🆔 Kompaniya #{company.id}")

    text = "\n".join(lines)
    for chat_id in _admin_chat_ids():
        try:
            await _send(chat_id, text)
        except Exception:  # noqa: BLE001 — xabar ketmasa ham tarif o'zgargan
            logger.exception("Tarif xabari yuborilmadi (chat %s)", chat_id)
