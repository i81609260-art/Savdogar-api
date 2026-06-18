"""Ucharbeksam — membership (tarif) bron qilish API."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import Base, get_db

router = APIRouter(prefix="/api/membership", tags=["Membership"])


# ── Model ──────────────────────────────────────────────────────────────────────

class MembershipBooking(Base):
    """Ucharbeksam membership bron."""

    __tablename__ = "membership_bookings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan = Column(String(50), nullable=False)          # standard / gold / platinum
    price = Column(String(20), nullable=False)          # "150$" / "450$" / "1500$"
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(255), nullable=True)
    people_count = Column(String(20), nullable=True)    # "4 ta" / "8 ta" / "Cheksiz"
    duration = Column(String(30), nullable=True)        # "4 oy" / "8 oy" / "1.5 yil"
    message = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="new")  # new / contacted / confirmed
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Schemas ────────────────────────────────────────────────────────────────────

class MembershipBookingCreate(BaseModel):
    plan: str = Field(..., min_length=1, max_length=50)
    price: str
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: str = Field(..., min_length=7, max_length=50)
    email: Optional[str] = None
    message: Optional[str] = None


PLANS = {
    "standard": {"price": "150$", "people_count": "4 ta",    "duration": "4 oy"},
    "gold":     {"price": "450$", "people_count": "8 ta",    "duration": "8 oy"},
    "platinum": {"price": "1500$","people_count": "Cheksiz", "duration": "1.5 yil"},
}


class MembershipBookingResponse(BaseModel):
    id: int
    plan: str
    price: str
    full_name: str
    phone: str
    email: Optional[str]
    people_count: Optional[str]
    duration: Optional[str]
    message: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=MembershipBookingResponse, summary="Membership bron qilish")
async def create_membership_booking(
    data: MembershipBookingCreate,
    db: AsyncSession = Depends(get_db),
) -> MembershipBookingResponse:
    """Ucharbeksam saytidan membership sotib olish so'rovi."""
    plan_key = data.plan.lower()
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri tarif: {data.plan}")

    plan_info = PLANS[plan_key]
    booking = MembershipBooking(
        plan=plan_key,
        price=plan_info["price"],
        full_name=data.full_name,
        phone=data.phone,
        email=data.email,
        people_count=plan_info["people_count"],
        duration=plan_info["duration"],
        message=data.message,
        status="new",
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return MembershipBookingResponse.model_validate(booking)


@router.get(
    "/admin",
    response_model=list[MembershipBookingResponse],
    summary="Admin: barcha membership bronlar",
)
async def list_membership_bookings(
    db: AsyncSession = Depends(get_db),
) -> list[MembershipBookingResponse]:
    """Admin paneli uchun barcha membership bronlarni ko'rish."""
    result = await db.execute(
        select(MembershipBooking).order_by(MembershipBooking.created_at.desc())
    )
    rows = result.scalars().all()
    return [MembershipBookingResponse.model_validate(r) for r in rows]


@router.patch(
    "/admin/{booking_id}/status",
    response_model=MembershipBookingResponse,
    summary="Admin: bron statusini o'zgartirish",
)
async def update_membership_status(
    booking_id: int,
    status: str,
    db: AsyncSession = Depends(get_db),
) -> MembershipBookingResponse:
    """Admin statusni yangilaydi: new / contacted / confirmed."""
    result = await db.execute(
        select(MembershipBooking).where(MembershipBooking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    if status not in ("new", "contacted", "confirmed"):
        raise HTTPException(status_code=400, detail="Noto'g'ri status")
    booking.status = status
    await db.commit()
    await db.refresh(booking)
    return MembershipBookingResponse.model_validate(booking)
