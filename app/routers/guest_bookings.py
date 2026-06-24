"""Guest booking API — no authentication required.

Allows public visitors (e.g. Ucharbeksam landing page) to create
bookings without logging in. A temporary user account is created
with role=USER if one doesn't already exist for the given phone.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.booking import BookingResponse
from app.services.notification_service import NotificationService
from app.utils.security import hash_password

router = APIRouter(prefix="/api/bookings", tags=["Guest Bookings"])


class GuestBookingCreate(BaseModel):
    """Public booking request — no auth needed."""

    tour_id: int
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=7, max_length=50)
    guests_count: int = Field(default=1, ge=1, le=20)
    notes: Optional[str] = None
    hotel_stars: Optional[str] = None
    bus_comfort: Optional[str] = None
    comment: Optional[str] = None


class GuestBookingResponse(BaseModel):
    """Simplified response for guest bookings."""

    id: int
    tour_title: Optional[str] = None
    status: str
    guests_count: int
    total_price: float
    message: str = "Bron muvaffaqiyatli qabul qilindi!"

    model_config = {"from_attributes": True}


@router.post(
    "/guest",
    response_model=GuestBookingResponse,
    summary="Mehmon sifatida bron qilish (authsiz)",
)
async def create_guest_booking(
    data: GuestBookingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GuestBookingResponse:
    """
    Public booking endpoint — no JWT required.

    Flow:
    1. Find or create a User with role=USER using the phone number.
    2. Validate tour exists and has capacity.
    3. Create a PENDING booking.
    4. Notify company staff.
    """
    # 1. Find the tour
    result = await db.execute(
        select(Tour)
        .options(selectinload(Tour.company))
        .where(Tour.id == data.tour_id, Tour.is_active == True)  # noqa: E712
    )
    tour = result.scalar_one_or_none()
    if not tour:
        raise HTTPException(status_code=404, detail="Tur topilmadi yoki faol emas")
    if tour.available_slots < data.guests_count:
        raise HTTPException(status_code=400, detail="Yetarli joy yo'q")

    # 2. Find or create user by phone
    clean_phone = data.phone.strip().replace(" ", "")
    user_result = await db.execute(
        select(User).where(User.phone == clean_phone)
    )
    user = user_result.scalar_one_or_none()

    if not user:
        # Create a guest user
        safe_email = f"guest_{clean_phone.replace('+', '')}@ucharbeksam.uz"
        # Check email uniqueness
        email_check = await db.execute(select(User).where(User.email == safe_email))
        existing_by_email = email_check.scalar_one_or_none()
        if existing_by_email:
            user = existing_by_email
        else:
            user = User(
                email=safe_email,
                hashed_password=hash_password(f"Guest_{clean_phone}!"),
                full_name=data.full_name.strip(),
                phone=clean_phone,
                role=UserRole.USER,
                is_active=True,
            )
            db.add(user)
            await db.flush()
    else:
        # Update name if changed
        if data.full_name.strip() and user.full_name != data.full_name.strip():
            user.full_name = data.full_name.strip()
            db.add(user)
            await db.flush()

    # 3. Build notes
    notes_parts = []
    if data.notes:
        notes_parts.append(data.notes)
    if data.comment:
        notes_parts.append(f"Izoh: {data.comment}")
    if data.hotel_stars:
        notes_parts.append(f"Mehmonxona: {data.hotel_stars} yulduz")
    if data.bus_comfort:
        notes_parts.append(f"Transfer: {data.bus_comfort}")
    notes_parts.append("Ucharbeksam saytidan bron qilindi")
    combined_notes = " | ".join(notes_parts)

    # 4. Create booking
    total_price = tour.price * data.guests_count
    booking = Booking(
        user_id=user.id,
        tour_id=tour.id,
        company_id=tour.company_id,
        status=BookingStatus.PENDING,
        guests_count=data.guests_count,
        total_price=total_price,
        phone=clean_phone,
        notes=combined_notes,
    )
    db.add(booking)
    await db.flush()

    # 5. Notify company staff
    try:
        sio = getattr(request.app.state, "sio", None)
        notifier = NotificationService(db, sio)
        await notifier.notify_company_staff(
            tour.company_id,
            "Yangi bron (saytdan)",
            f"{data.full_name} «{tour.title}» turiga {data.guests_count} kishi uchun bron qildi",
            "booking",
            "/bookings",
        )
    except Exception:
        pass  # Don't fail the booking if notification fails

    await db.commit()
    await db.refresh(booking)

    return GuestBookingResponse(
        id=booking.id,
        tour_title=tour.title,
        status=booking.status.value if hasattr(booking.status, "value") else str(booking.status),
        guests_count=booking.guests_count,
        total_price=booking.total_price,
        message=f"Bron #{booking.id} muvaffaqiyatli qabul qilindi! Tez orada bog'lanamiz.",
    )
