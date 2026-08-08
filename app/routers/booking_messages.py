"""Bron bo'yicha yozishuv: `GET/POST /api/bookings/{id}/messages`.

Ruxsat qoidasi butun fayl bo'ylab BITTA joyda hal qilinadi
(`_booking_for_user`): suhbatni faqat o'sha bronning ikki tomoni ko'radi —
bronni qilgan mijoz va bron tegishli firmaning xodimi. Boshqa hech kim,
jumladan boshqa firmaning admini ham, xabarlarni ko'ra olmaydi va yoza
olmaydi.

Bu tekshiruv har bir endpointda takrorlanmasligi kerak edi: takrorlansa
ertaga qo'shiladigan to'rtinchi endpointda unutilishi mumkin, natijada
savdo siri sizib chiqadi.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.booking import Booking
from app.models.booking_message import BookingMessage, MessageSender
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/bookings", tags=["Bron yozishuvi"])

# Uzun matn chat emas — hujjat. Cheklov bazani ham, interfeysni ham asraydi.
MAX_LEN = 2000


class MessageOut(BaseModel):
    id: int
    booking_id: int
    sender_role: MessageSender
    text: str
    created_at: Optional[datetime]
    read_at: Optional[datetime]
    is_mine: bool


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_LEN)


async def _booking_for_user(
    db: AsyncSession, booking_id: int, user: User
) -> tuple[Booking, MessageSender]:
    """Bronni topadi va foydalanuvchi qaysi tomon ekanini aniqlaydi.

    Topilmaslik va ruxsat yo'qligi BIR XIL javob beradi (404). Aks holda
    javob kodining o'zi ma'lumot berardi: 403 olgan odam "bunday bron bor,
    lekin meniki emas" degan xulosaga kelardi.
    """
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()
    if booking is None:
        raise HTTPException(status_code=404, detail="Bron topilmadi")

    # Mijoz — bronni qilgan odam.
    if booking.user_id == user.id:
        return booking, MessageSender.CUSTOMER

    # Agentlik tomoni — o'sha firmaning xodimi.
    staff_roles = (UserRole.ADMIN, UserRole.OPERATOR)
    if user.company_id == booking.company_id and user.role in staff_roles:
        return booking, MessageSender.AGENCY

    raise HTTPException(status_code=404, detail="Bron topilmadi")


def _out(message: BookingMessage, me: MessageSender) -> MessageOut:
    return MessageOut(
        id=message.id,
        booking_id=message.booking_id,
        sender_role=message.sender_role,
        text=message.text,
        created_at=message.created_at,
        read_at=message.read_at,
        is_mine=message.sender_role == me,
    )


@router.get("/{booking_id}/messages", summary="Yozishuvni ochish")
async def list_messages(
    booking_id: int,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    _, me = await _booking_for_user(db, booking_id, current_user)

    rows = (
        await db.execute(
            select(BookingMessage)
            .where(BookingMessage.booking_id == booking_id)
            .order_by(BookingMessage.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    # Bazadan oxirgilari olinadi, ekranda esa eskisidan yangisiga qarab
    # ko'rsatiladi — shuning uchun teskari qaytaramiz.
    return [_out(m, me) for m in reversed(rows)]


@router.post("/{booking_id}/messages", status_code=201, summary="Xabar yuborish")
async def send_message(
    booking_id: int,
    payload: MessageIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    booking, me = await _booking_for_user(db, booking_id, current_user)

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Xabar bo'sh")

    message = BookingMessage(
        company_id=booking.company_id,
        booking_id=booking.id,
        sender_role=me,
        sender_user_id=current_user.id,
        text=text,
    )
    db.add(message)
    await db.flush()
    await db.refresh(message)

    await _notify(booking, message)
    return _out(message, me)


@router.post("/{booking_id}/messages/read", summary="O'qilgan deb belgilash")
async def mark_read(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """QARSHI tomon yozgan xabarlarni o'qilgan deb belgilaydi.

    O'z xabarini o'qilgan deb belgilash mantiqsiz — shuning uchun shart
    `sender_role != me`.
    """
    booking, me = await _booking_for_user(db, booking_id, current_user)

    result = await db.execute(
        update(BookingMessage)
        .where(
            BookingMessage.booking_id == booking_id,
            BookingMessage.sender_role != me,
            BookingMessage.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.flush()

    await _notify_read(booking, me)
    return {"belgilandi": result.rowcount or 0}


# --------------------------------------------------------------------------
# Real-time
# --------------------------------------------------------------------------
# Socket xonalari allaqachon mavjud (`company_{id}`, `user_{id}`) va bron
# holati ular orqali yuboriladi. Yozishuv ham o'shalarni ishlatadi — yangi
# ulanish mantiqini yozish shart emas.
#
# `sio` import qilinishi KECHIKTIRILGAN: `app.main` bu routerni import
# qiladi, teskari import esa aylanma bog'liqlik hosil qilardi.
async def _notify(booking: Booking, message: BookingMessage) -> None:
    sio = _sio()
    if sio is None:
        return
    payload = {
        "booking_id": booking.id,
        "message_id": message.id,
        "sender_role": str(message.sender_role),
        "text": message.text,
    }
    await sio.emit("message_new", payload, room=f"company_{booking.company_id}")
    await sio.emit("message_new", payload, room=f"user_{booking.user_id}")


async def _notify_read(booking: Booking, reader: MessageSender) -> None:
    sio = _sio()
    if sio is None:
        return
    payload = {"booking_id": booking.id, "reader": str(reader)}
    await sio.emit("message_read", payload, room=f"company_{booking.company_id}")
    await sio.emit("message_read", payload, room=f"user_{booking.user_id}")


def _sio():
    try:
        from app.main import sio

        return sio
    except Exception:  # noqa: BLE001 — testlarda socket bo'lmasligi mumkin
        return None
