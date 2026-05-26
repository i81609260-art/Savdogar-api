"""Telegram bot service — httpx orqali Telegram API bilan ishlash."""

from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.booking import Booking, BookingStatus
from app.models.tour import Tour
from app.models.user import User
from app.utils.security import verify_password


class TelegramBotService:
    """Handles incoming Telegram updates and replies via Telegram HTTP API."""

    def __init__(self, db: AsyncSession, token: str, sio=None):
        self.db = db
        self.token = token
        self.sio = sio
        self._api = f"https://api.telegram.org/bot{token}"

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    async def handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()

        if text.startswith("/start"):
            await self._cmd_start(chat_id)
        elif text.startswith("/link"):
            await self._cmd_link(chat_id, text)
        elif text.startswith("/turlar"):
            await self._cmd_tours(chat_id)
        elif text.startswith("/bron"):
            await self._cmd_book(chat_id, text)
        elif text.startswith("/bronlarim"):
            await self._cmd_my_bookings(chat_id)
        elif text.startswith("/kutish"):
            await self._cmd_waitlist(chat_id, text)
        else:
            await self._send(chat_id, "❓ Buyruqlar:\n/turlar — turlar ro'yxati\n/bron TOUR_ID — bron qilish\n/bronlarim — bronlarim\n/kutish TOUR_ID — navbatga yozilish")

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    async def _cmd_start(self, chat_id: str) -> None:
        await self._send(
            chat_id,
            "👋 <b>Savdogar botiga xush kelibsiz!</b>\n\n"
            "Hisobingizni ulash uchun:\n"
            "<code>/link EMAIL PAROL</code>\n\n"
            "Masalan:\n"
            "<code>/link user@example.com Parol123</code>",
        )

    async def _cmd_link(self, chat_id: str, text: str) -> None:
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            await self._send(chat_id, "❌ To'liq kiriting: <code>/link EMAIL PAROL</code>")
            return

        email, password = parts[1], parts[2]
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            await self._send(chat_id, "❌ Email yoki parol noto'g'ri")
            return

        user.telegram_chat_id = chat_id
        await self.db.commit()
        await self._send(
            chat_id,
            f"✅ <b>{user.full_name}</b>, hisobingiz ulandi!\n\n"
            "/turlar — mavjud turlar\n"
            "/bronlarim — bronlaringiz",
        )

    async def _cmd_tours(self, chat_id: str) -> None:
        result = await self.db.execute(
            select(Tour)
            .where(Tour.is_active == True, Tour.available_slots > 0)  # noqa: E712
            .order_by(Tour.start_date)
            .limit(10)
        )
        tours = result.scalars().all()

        if not tours:
            await self._send(chat_id, "📭 Hozircha mavjud tur yo'q")
            return

        lines = ["🗺 <b>Mavjud turlar:</b>\n"]
        for t in tours:
            lines.append(
                f"<b>#{t.id}</b> {t.title}\n"
                f"   📍 {t.city}  |  📅 {t.start_date}  |  👥 {t.available_slots} joy\n"
                f"   💰 {t.price:,.0f} so'm\n"
            )
        lines.append("Bron qilish: <code>/bron TOUR_ID</code>")
        await self._send(chat_id, "\n".join(lines))

    async def _cmd_book(self, chat_id: str, text: str) -> None:
        user = await self._get_user(chat_id)
        if not user:
            return

        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await self._send(chat_id, "❌ Foydalanish: <code>/bron TOUR_ID</code>")
            return

        tour_id = int(parts[1])
        guests = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1

        result = await self.db.execute(
            select(Tour).options(selectinload(Tour.company)).where(Tour.id == tour_id, Tour.is_active == True)  # noqa: E712
        )
        tour = result.scalar_one_or_none()
        if not tour:
            await self._send(chat_id, "❌ Tur topilmadi")
            return
        if tour.available_slots < guests:
            await self._send(chat_id, f"❌ Yetarli joy yo'q. Mavjud: {tour.available_slots}")
            return

        booking = Booking(
            user_id=user.id,
            tour_id=tour.id,
            company_id=tour.company_id,
            status=BookingStatus.PENDING,
            guests_count=guests,
            total_price=tour.price * guests,
        )
        self.db.add(booking)
        await self.db.commit()
        await self.db.refresh(booking)

        await self._send(
            chat_id,
            f"✅ <b>Bron qabul qilindi!</b>\n\n"
            f"🎫 Bron #{booking.id}\n"
            f"🗺 {tour.title}\n"
            f"📅 {tour.start_date} — {tour.end_date}\n"
            f"👥 {guests} mehmon\n"
            f"💰 {booking.total_price:,.0f} so'm\n\n"
            f"⏳ Status: Kutilmoqda — firma tasdiqlaydi",
        )

    async def _cmd_my_bookings(self, chat_id: str) -> None:
        user = await self._get_user(chat_id)
        if not user:
            return

        result = await self.db.execute(
            select(Booking)
            .options(selectinload(Booking.tour))
            .where(Booking.user_id == user.id)
            .order_by(Booking.created_at.desc())
            .limit(5)
        )
        bookings = result.scalars().all()

        if not bookings:
            await self._send(chat_id, "📭 Sizda hali bron yo'q")
            return

        status_emoji = {"confirmed": "✅", "pending": "⏳", "cancelled": "❌"}
        lines = ["🎫 <b>Bronlaringiz:</b>\n"]
        for b in bookings:
            emoji = status_emoji.get(b.status.value, "❓")
            title = b.tour.title if b.tour else f"Tur #{b.tour_id}"
            lines.append(f"{emoji} <b>#{b.id}</b> {title} — {b.total_price:,.0f} so'm")
        await self._send(chat_id, "\n".join(lines))

    async def _cmd_waitlist(self, chat_id: str, text: str) -> None:
        user = await self._get_user(chat_id)
        if not user:
            return

        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await self._send(chat_id, "❌ Foydalanish: <code>/kutish TOUR_ID</code>")
            return

        from app.models.waitlist import Waitlist

        tour_id = int(parts[1])
        result = await self.db.execute(select(Tour).where(Tour.id == tour_id))
        tour = result.scalar_one_or_none()
        if not tour:
            await self._send(chat_id, "❌ Tur topilmadi")
            return

        existing = await self.db.execute(
            select(Waitlist).where(Waitlist.user_id == user.id, Waitlist.tour_id == tour_id)
        )
        if existing.scalar_one_or_none():
            await self._send(chat_id, "ℹ️ Siz allaqachon navbatdasiz. Joy bo'shaganda xabar berамиз.")
            return

        wl = Waitlist(user_id=user.id, tour_id=tour_id, company_id=tour.company_id)
        self.db.add(wl)
        await self.db.commit()
        await self._send(chat_id, f"⏰ <b>{tour.title}</b> turiga navbatga yozildingiz!\nJoy bo'shaganda darhol xabar beramiz.")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _get_user(self, chat_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_chat_id == chat_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await self._send(
                chat_id,
                "🔐 Avval hisobingizni ulang:\n<code>/link EMAIL PAROL</code>",
            )
        return user

    async def _send(self, chat_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self._api}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
