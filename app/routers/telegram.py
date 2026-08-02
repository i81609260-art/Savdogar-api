"""Telegram bot webhook va sozlash endpointlari."""

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import UserRole
from app.services.telegram_service import TelegramBotService

router = APIRouter(prefix="/api/telegram", tags=["Telegram Bot"])
logger = logging.getLogger(__name__)


def _sio(request: Request):
    return getattr(request.app.state, "sio", None)


@router.post("/webhook", summary="Telegram webhook (Telegram chaqiradi)")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Platforma botining yangilanishlari.

    So'rov haqiqatan Telegram'dan kelganini `secret_token` sarlavhasi
    tasdiqlaydi — ilgari bu endpoint butunlay ochiq edi va istalgan odam soxta
    "xabar" yuborib botni boshqara olardi.

    Sarlavha `setWebhook` chaqirilganda o'rnatiladi: superadmin bir marta
    `POST /api/telegram/set-webhook` ni chaqirishi kerak.
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"ok": False, "reason": "bot not configured"}

    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not hmac.compare_digest(secret or "", settings.telegram_webhook_secret):
        logger.warning(
            "Telegram webhook imzosiz so'rov rad etildi. Superadmin "
            "POST /api/telegram/set-webhook ni bir marta chaqirsin."
        )
        return {"ok": False, "reason": "invalid secret"}

    update = await request.json()
    service = TelegramBotService(db, settings.telegram_bot_token, _sio(request))
    await service.handle_update(update)
    return {"ok": True}


@router.post(
    "/set-webhook",
    summary="Telegram webhookni ro'yxatdan o'tkazish (admin)",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def set_webhook(request: Request) -> dict:
    """Register this server's URL as the Telegram webhook."""
    import httpx

    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN sozlanmagan")

    webhook_url = f"{settings.savdogar_public_url.rstrip('/')}/api/telegram/webhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={
                "url": webhook_url,
                # Telegram shu qiymatni har so'rov sarlavhasida qaytaradi —
                # webhook endpointi aynan shuni tekshiradi.
                "secret_token": settings.telegram_webhook_secret,
            },
        )
    return resp.json()


@router.get(
    "/info",
    summary="Telegram bot ma'lumoti",
    dependencies=[Depends(role_required(UserRole.SUPERADMIN))],
)
async def bot_info() -> dict:
    import httpx

    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN sozlanmagan")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/getMe"
        )
    return resp.json()
