"""Telegram bot webhook va sozlash endpointlari."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import UserRole
from app.services.telegram_service import TelegramBotService

router = APIRouter(prefix="/api/telegram", tags=["Telegram Bot"])


def _sio(request: Request):
    return getattr(request.app.state, "sio", None)


@router.post("/webhook", summary="Telegram webhook (Telegram chaqiradi)")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"ok": False, "reason": "bot not configured"}

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

    webhook_url = f"{settings.savdogar_public_url}/api/telegram/webhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
            json={"url": webhook_url},
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
