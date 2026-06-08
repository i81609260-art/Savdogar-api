"""Telegram WebApp mini app for tour booking."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from pydantic import BaseModel

router = APIRouter(prefix="/api/telegram", tags=["Telegram Mini App"])


class TelegramUserData(BaseModel):
    """Telegram user data from WebApp."""

    id: int
    username: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    photo_url: Optional[str] = None


class BookingRequest(BaseModel):
    """Booking request from Telegram WebApp."""

    tour_id: int
    phone: str
    first_name: str
    last_name: str
    group_size: int
    start_date: str


@router.get("/companies/{company_id}/mini-app-config", summary="Mini app config")
async def get_miniapp_config(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get mini app configuration for company."""
    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    return {
        "company_id": company.id,
        "company_name": company.name,
        "logo_url": company.logo_url,
        "description": "Savdogar Tur Booking",
        "support_chat": f"@{company.name}",
        "features": {
            "tours": True,
            "booking": True,
            "my_bookings": True,
            "support": True,
        },
    }


@router.post("/booking", summary="Telegram'dan bron qilish")
async def create_booking_from_telegram(
    data: BookingRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Telegram WebApp'dan bron yaratish."""
    from app.models.booking import Booking

    result = await db.execute(
        select(Tour).where(Tour.id == data.tour_id)
    )
    tour = result.scalar_one_or_none()

    if not tour:
        raise HTTPException(status_code=404, detail="Tur topilmadi")

    # Create booking
    booking = Booking(
        tour_id=data.tour_id,
        company_id=tour.company_id,
        customer_name=f"{data.first_name} {data.last_name}",
        customer_phone=data.phone,
        group_size=data.group_size,
        start_date=data.start_date,
        status="pending",
        source="telegram",
        total_price=tour.price * data.group_size,
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    return {
        "booking_id": booking.id,
        "status": "pending",
        "total_price": booking.total_price,
        "message": "Bron qabul qilindi! Admin tez orada sizga bog'lanadi.",
    }


@router.get("/tours/{company_id}", summary="Kompaniya turlari")
async def get_company_tours(
    company_id: int,
    db: AsyncSession = Depends(get_db),
) -> list:
    """Get all active tours for company (for mini app)."""
    result = await db.execute(
        select(Tour)
        .where(Tour.company_id == company_id)
        .where(Tour.status == "active")
    )
    tours = result.scalars().all()

    return [
        {
            "id": tour.id,
            "title": tour.title,
            "destination": tour.destination,
            "price": tour.price,
            "duration_days": tour.duration_days,
            "image_url": tour.image_url,
            "rating": tour.rating,
        }
        for tour in tours
    ]


@router.get("/tours/{tour_id}/details", summary="Tur detallari")
async def get_tour_details(
    tour_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get detailed tour information."""
    result = await db.execute(
        select(Tour).where(Tour.id == tour_id)
    )
    tour = result.scalar_one_or_none()

    if not tour:
        raise HTTPException(status_code=404, detail="Tur topilmadi")

    return {
        "id": tour.id,
        "title": tour.title,
        "destination": tour.destination,
        "description": tour.description,
        "price": tour.price,
        "duration_days": tour.duration_days,
        "max_persons": tour.max_persons,
        "image_url": tour.image_url,
        "hotel_rating": tour.hotel_rating,
        "meal_plan": tour.meal_plan,
        "tour_type": tour.tour_type,
        "rating": tour.rating,
        "available_dates": tour.available_dates,
    }


from typing import Optional
from app.models.tour import Tour
