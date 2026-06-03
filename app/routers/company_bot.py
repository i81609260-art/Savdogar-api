"""Per-company Telegram bot endpoints: connect, disconnect, status, webhook."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.company_telegram_bot import CompanyTelegramBot
from app.models.user import User, UserRole

settings = get_settings()

admin_router = APIRouter(prefix="/api/admin/telegram", tags=["Company Telegram Bot"])
webhook_router = APIRouter(prefix="/api/telegram", tags=["Telegram Webhooks"])

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


async def _tg(token: str, method: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(TELEGRAM_API.format(token=token, method=method), json=kwargs)
        return r.json()


# ── Admin endpoints ────────────────────────────────────────────────────────────

@admin_router.get("/status", summary="Bot holati")
async def bot_status(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(CompanyTelegramBot).where(CompanyTelegramBot.company_id == current_user.company_id)
    )
    bot = result.scalar_one_or_none()
    if not bot:
        return {"connected": False}
    return {
        "connected": True,
        "bot_username": bot.bot_username,
        "webhook_set": bot.webhook_set,
        "is_active": bot.is_active,
    }


@admin_router.post("/connect", summary="Bot tokenini ulash")
async def connect_bot(
    payload: dict,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = (payload.get("bot_token") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="bot_token majburiy")

    # Validate token via Telegram API
    me = await _tg(token, "getMe")
    if not me.get("ok"):
        raise HTTPException(status_code=400, detail="Noto'g'ri bot token. BotFather dan token oling.")

    username = me["result"].get("username", "")

    # Upsert
    result = await db.execute(
        select(CompanyTelegramBot).where(CompanyTelegramBot.company_id == current_user.company_id)
    )
    bot = result.scalar_one_or_none()
    if bot:
        bot.bot_token = token
        bot.bot_username = username
        bot.webhook_set = False
        bot.is_active = True
    else:
        bot = CompanyTelegramBot(
            company_id=current_user.company_id,
            bot_token=token,
            bot_username=username,
        )
        db.add(bot)

    await db.flush()

    # Set webhook
    webhook_url = f"{settings.savdogar_public_url}/api/telegram/company-webhook/{token}"
    wh = await _tg(token, "setWebhook", url=webhook_url)
    bot.webhook_set = wh.get("ok", False)

    await db.commit()
    await db.refresh(bot)

    return {
        "connected": True,
        "bot_username": bot.bot_username,
        "webhook_set": bot.webhook_set,
        "link": f"https://t.me/{username}",
    }


@admin_router.delete("/disconnect", summary="Botni o'chirish")
async def disconnect_bot(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(CompanyTelegramBot).where(CompanyTelegramBot.company_id == current_user.company_id)
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot topilmadi")
    try:
        await _tg(bot.bot_token, "deleteWebhook")
    except Exception:
        pass
    await db.delete(bot)
    await db.commit()
    return {"disconnected": True}


# ── Webhook handler ────────────────────────────────────────────────────────────

@webhook_router.post(
    "/company-webhook/{bot_token}",
    summary="Company bot webhook (Telegram chaqiradi)",
    include_in_schema=False,
)
async def company_webhook(
    bot_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(CompanyTelegramBot).where(
            CompanyTelegramBot.bot_token == bot_token,
            CompanyTelegramBot.is_active.is_(True),
        )
    )
    bot = result.scalar_one_or_none()
    if not bot:
        return {"ok": False}

    update = await request.json()
    await _handle_company_update(bot_token, bot.company_id, update, db)
    return {"ok": True}


# ── Bot logic ──────────────────────────────────────────────────────────────────

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🗺 Turlar"}, {"text": "ℹ️ Biz haqimizda"}],
        [{"text": "📞 Bog'lanish"}, {"text": "🌐 Sayt"}],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}


async def _send(token: str, chat_id, text: str, reply_markup=None) -> None:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _tg(token, "sendMessage", **payload)


async def _send_photo(token: str, chat_id, photo_url: str, caption: str, reply_markup=None) -> None:
    payload: dict = {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = await _tg(token, "sendPhoto", **payload)
    # If photo failed (bad URL etc.), fall back to text
    if not result.get("ok"):
        await _send(token, chat_id, caption, reply_markup)


async def _handle_company_update(token: str, company_id: int, update: dict, db: AsyncSession) -> None:
    from sqlalchemy import select
    from app.models.company import Company
    from app.models.tour import Tour

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    # Load company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return

    site_url = f"https://savdogar-sable.vercel.app/companies/{company_id}"
    if company.slug:
        site_url = f"https://savdogar-sable.vercel.app/sites/{company.slug}"

    # Route commands/text
    if text in ("/start", "/boshlash"):
        welcome = (
            f"👋 <b>{company.name}</b> botiga xush kelibsiz!\n\n"
            f"📍 {company.city}\n"
        )
        if company.description:
            welcome += f"\n{company.description}\n"
        welcome += "\nQuyidagi menyu orqali biz bilan tanishing 👇"

        if company.logo_url:
            await _send_photo(token, chat_id, company.logo_url, welcome, reply_markup=MAIN_KEYBOARD)
        else:
            await _send(token, chat_id, welcome, reply_markup=MAIN_KEYBOARD)

    elif text in ("🗺 Turlar", "/turlar"):
        res = await db.execute(
            select(Tour).where(
                Tour.company_id == company_id,
                Tour.is_active.is_(True),
                Tour.available_slots > 0,
            ).order_by(Tour.start_date).limit(8)
        )
        tours = res.scalars().all()
        if not tours:
            await _send(token, chat_id, "😔 Hozircha faol turlar yo'q.", reply_markup=MAIN_KEYBOARD)
            return
        lines = ["🗺 <b>Bizning turlar:</b>\n"]
        for t in tours:
            lines.append(
                f"✈️ <b>{t.title}</b>\n"
                f"   📍 {t.city}, {t.country}\n"
                f"   🕐 {t.duration_days} kun  |  💰 ${t.price:,.0f}\n"
                f"   🎫 {t.available_slots} ta joy qoldi\n"
            )
        lines.append(f"\n🔗 Batafsil: {site_url}")
        await _send(token, chat_id, "\n".join(lines), reply_markup=MAIN_KEYBOARD)

    elif text in ("ℹ️ Biz haqimizda", "/haqimizda"):
        desc = company.description or "Sifatli sayohat xizmatlari."
        await _send(
            token, chat_id,
            f"ℹ️ <b>{company.name}</b>\n\n{desc}",
            reply_markup=MAIN_KEYBOARD,
        )

    elif text in ("📞 Bog'lanish", "/boglanish"):
        await _send(
            token, chat_id,
            f"📞 <b>Biz bilan bog'laning:</b>\n\n"
            f"📍 Shahar: {company.city}\n"
            f"📞 Tel: <a href='tel:{company.phone}'>{company.phone}</a>\n"
            f"📧 Email: {company.email}",
            reply_markup=MAIN_KEYBOARD,
        )

    elif text in ("🌐 Sayt", "/sayt"):
        await _send(
            token, chat_id,
            f"🌐 <b>Bizning sayt:</b>\n{site_url}",
            reply_markup=MAIN_KEYBOARD,
        )

    else:
        await _send(
            token, chat_id,
            "Menyu orqali tanlang 👇",
            reply_markup=MAIN_KEYBOARD,
        )
