"""Per-company Telegram bot endpoints: connect, disconnect, status, webhook."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pydantic import BaseModel
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


class BotTokenRequest(BaseModel):
    """Request model for bot token."""
    bot_token: str


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
    payload: BotTokenRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token = (payload.bot_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="bot_token majburiy")

    # Validate token via Telegram API
    me = await _tg(token, "getMe")
    if not me.get("ok"):
        raise HTTPException(status_code=400, detail="Noto'g'ri bot token. BotFather dan token oling.")

    username = me["result"].get("username", "")

    # Check if token is already used by another company
    existing = await db.execute(
        select(CompanyTelegramBot).where(
            (CompanyTelegramBot.bot_token == token) &
            (CompanyTelegramBot.company_id != current_user.company_id)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Bu bot token boshqa kompaniya tomonidan ishlatilmoqda")

    # Upsert
    result = await db.execute(
        select(CompanyTelegramBot).where(CompanyTelegramBot.company_id == current_user.company_id)
    )
    bot = result.scalar_one_or_none()
    if bot:
        # If updating, delete old record first to avoid UNIQUE constraint
        await db.delete(bot)
        await db.flush()

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

# In-memory dictionary to track conversational booking states per user
_user_states: dict[int, dict] = {}

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🗺 Turlar"}],
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
    from app.models.user import User, UserRole
    from app.models.booking import Booking, BookingStatus
    from app.services.notification_service import NotificationService
    from app.utils.security import hash_password

    # Check callback query for inline buttons (tour selection)
    cb = update.get("callback_query")
    if cb:
        cb_id = cb["id"]
        chat_id = cb["message"]["chat"]["id"]
        data = cb.get("data", "")

        await _tg(token, "answerCallbackQuery", callback_query_id=cb_id)

        if data.startswith("book_"):
            tour_id = int(data.split("_")[1])
            res = await db.execute(select(Tour).where(Tour.id == tour_id, Tour.company_id == company_id))
            tour = res.scalar_one_or_none()
            if not tour:
                await _send(token, chat_id, "❌ Kechirasiz, ushbu tur topilmadi.", reply_markup=MAIN_KEYBOARD)
                return

            _user_states[chat_id] = {
                "step": "get_name",
                "tour_id": tour.id,
                "tour_title": tour.title,
            }
            await _send(
                token, chat_id,
                f"✈️ <b>{tour.title}</b> tanlandi.\n\n✍️ Bron qilish uchun ismingiz va familiyangizni kiriting (masalan: Ali Valiyev):",
                reply_markup={"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
            )
        return

    # Check normal text message or contact share
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    contact = msg.get("contact")

    # Load company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if not company:
        return

    site_url = f"https://savdogar-sable.vercel.app/companies/{company_id}"
    if company.slug:
        site_url = f"https://savdogar-sable.vercel.app/sites/{company.slug}"

    # Handle cancellation
    if text in ("/cancel", "❌ Bekor qilish"):
        _user_states.pop(chat_id, None)
        await _send(token, chat_id, "❌ Bron qilish bekor qilindi.", reply_markup=MAIN_KEYBOARD)
        return

    # Handle conversational states
    state = _user_states.get(chat_id)
    if state:
        step = state["step"]

        if step == "get_name":
            if len(text.split()) < 2:
                await _send(token, chat_id, "⚠️ Iltimos, ism va familiyangizni to'liq kiriting (masalan: Ali Valiyev):")
                return
            state["name"] = text
            state["step"] = "get_phone"
            phone_keyboard = {
                "keyboard": [
                    [{"text": "📱 Telefon raqamni yuborish", "request_contact": True}],
                    [{"text": "❌ Bekor qilish"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            await _send(
                token, chat_id,
                f"📞 Rahmat, {text}.\nEndi telefon raqamingizni kiriting yoki quyidagi tugmani bosish orqali yuboring:",
                reply_markup=phone_keyboard
            )
            return

        elif step == "get_phone":
            phone = ""
            if contact:
                phone = contact.get("phone_number", "")
            else:
                phone = text

            clean_phone = phone.strip().replace(" ", "").replace("-", "")
            if not clean_phone or len(clean_phone) < 7:
                await _send(token, chat_id, "⚠️ Iltimos, to'g'ri telefon raqam kiriting:")
                return

            state["phone"] = clean_phone
            state["step"] = "get_guests"
            guests_keyboard = {
                "keyboard": [
                    [{"text": "1"}, {"text": "2"}, {"text": "3"}, {"text": "4"}],
                    [{"text": "❌ Bekor qilish"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            await _send(
                token, chat_id,
                "👥 Necha kishi uchun joy bron qilmoqchisiz? (Faqat raqam kiriting, masalan: 2):",
                reply_markup=guests_keyboard
            )
            return

        elif step == "get_guests":
            try:
                guests = int(text)
                if guests < 1 or guests > 100:
                    raise ValueError()
            except ValueError:
                await _send(token, chat_id, "⚠️ Iltimos, faqat raqam kiriting (masalan: 3):")
                return

            tour_id = state["tour_id"]
            tour_res = await db.execute(select(Tour).where(Tour.id == tour_id))
            tour = tour_res.scalar_one_or_none()
            if not tour:
                _user_states.pop(chat_id, None)
                await _send(token, chat_id, "❌ Kechirasiz, tur topilmadi.", reply_markup=MAIN_KEYBOARD)
                return

            # Find or create user
            user_res = await db.execute(select(User).where(User.phone == state["phone"]))
            user = user_res.scalar_one_or_none()
            if not user:
                safe_email = f"tg_{state['phone'].replace('+', '')}@savdogar.uz"
                email_check = await db.execute(select(User).where(User.email == safe_email))
                existing_email = email_check.scalar_one_or_none()
                if existing_email:
                    user = existing_email
                else:
                    user = User(
                        email=safe_email,
                        hashed_password=hash_password(f"Tg_{state['phone']}!"),
                        full_name=state["name"],
                        phone=state["phone"],
                        role=UserRole.USER,
                        is_active=True,
                    )
                    db.add(user)
                    await db.flush()

            # Create Booking
            total_price = tour.price * guests
            booking = Booking(
                user_id=user.id,
                tour_id=tour.id,
                company_id=company_id,
                status=BookingStatus.PENDING,
                guests_count=guests,
                total_price=total_price,
                phone=state["phone"],
                notes=f"Telegram bot orqali bron qilindi. Buyurtmachi: {state['name']}",
            )
            db.add(booking)
            await db.flush()

            # Notify company staff
            try:
                notifier = NotificationService(db, None)
                await notifier.notify_company_staff(
                    company_id,
                    "Yangi bron (Telegram bot)",
                    f"{state['name']} «{tour.title}» turiga {guests} kishi uchun bron qildi",
                    "booking",
                    "/bookings",
                )
            except Exception as e:
                print("Staff notification failed:", e)

            await db.commit()
            await db.refresh(booking)

            # Clear state
            _user_states.pop(chat_id, None)

            # Success text
            success_text = (
                f"✅ <b>Broningiz muvaffaqiyatli qabul qilindi!</b>\n\n"
                f"📑 Bron ID: <code>#{booking.id}</code>\n"
                f"✈️ Tur: <b>{tour.title}</b>\n"
                f"👥 Mehmonlar soni: <b>{guests} kishi</b>\n"
                f"💰 Umumiy narx: <b>${total_price:,.0f}</b>\n\n"
                f"📞 Yaqin daqiqalar ichida operatorimiz siz bilan bog'lanadi."
            )
            await _send(token, chat_id, success_text, reply_markup=MAIN_KEYBOARD)
            return

    # Route normal menu commands
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

        lines = [
            "🗺 <b>Bizning faol turlarimiz:</b>\n",
            "Quyidagi turlardan birini tanlab, bot orqali to'g'ridan-to'g'ri bron qilishingiz mumkin 👇"
        ]

        inline_buttons = []
        for t in tours:
            inline_buttons.append([
                {"text": f"✈️ {t.title} (${t.price:,.0f})", "callback_data": f"book_{t.id}"}
            ])

        reply_markup = {"inline_keyboard": inline_buttons}
        await _send(token, chat_id, "\n".join(lines), reply_markup=reply_markup)

    elif text in ("📞 Bog'lanish", "/boglanish"):
        await _send(
            token, chat_id,
            f"📞 <b>Biz bilan bog'laning:</b>\n\n"
            f"📍 Shahar: {company.city}\n"
            f"📞 Tel: <a href='tel:{company.phone}'>{company.phone}</a>\n"
            f"📧 Email: {company.email or 'mavjud emas'}",
            reply_markup=MAIN_KEYBOARD,
        )

    elif text in ("🌐 Sayt", "/sayt"):
        site_markup = {
            "inline_keyboard": [
                [{"text": "🌐 Saytga o'tish", "url": site_url}]
            ]
        }
        await _send(
            token, chat_id,
            f"🌐 <b>Bizning sayt:</b>\n{site_url}",
            reply_markup=site_markup,
        )

    else:
        await _send(
            token, chat_id,
            "Menyu orqali tanlang 👇",
            reply_markup=MAIN_KEYBOARD,
        )
