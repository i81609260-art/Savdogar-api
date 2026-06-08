"""Create tour packages from individual tour requests."""

from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.models.tour import Tour
from pydantic import BaseModel

router = APIRouter(prefix="/api/tour-creator", tags=["Tour Creator"])


class CreateTourFromRequestData(BaseModel):
    """Create tour from request."""

    request_id: int
    tour_name: str
    description: Optional[str] = None
    price: float
    max_persons: Optional[int] = None
    image_url: Optional[str] = None


@router.post("", summary="So'rovdan tur paket yaratish")
async def create_tour_from_request(
    data: CreateTourFromRequestData,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """So'rovdan tur paketini yaratish."""
    from app.models.request import TourRequest

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    # Validate request exists
    result = await db.execute(
        select(TourRequest).where(
            and_(
                TourRequest.id == data.request_id,
                TourRequest.company_id == current_user.company_id,
            )
        )
    )
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="So'rov topilmadi")

    # Create tour from request
    tour = Tour(
        company_id=current_user.company_id,
        title=data.tour_name,
        destination=request.destination or data.tour_name,
        description=data.description or f"So'rovdan yaratilgan tur: {request.lead_name}",
        price=data.price,
        duration_days=getattr(request, "duration_days", 5),
        max_persons=data.max_persons or request.group_size or 20,
        image_url=data.image_url,
        status="active",
        hotel_rating=request.hotel_rating,
        meal_plan=request.meal_plan,
        tour_type=request.tour_type,
        source_request_id=data.request_id,
    )

    db.add(tour)
    await db.commit()
    await db.refresh(tour)

    # Update request status
    request.status = "To'landi"
    await db.commit()

    return {
        "id": tour.id,
        "title": tour.title,
        "price": tour.price,
        "status": "created",
    }


@router.get("/request/{request_id}/suggested-price", summary="So'rovdan taklif etilgan narx")
async def get_suggested_price(
    request_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """So'rovga asosan taklif etilgan narxni olish."""
    from app.models.request import TourRequest
    from app.services.pricing_calculator import PricingCalculator

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    result = await db.execute(
        select(TourRequest).where(
            and_(
                TourRequest.id == request_id,
                TourRequest.company_id == current_user.company_id,
            )
        )
    )
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="So'rov topilmadi")

    pricing = PricingCalculator.calculate_price(
        destination=request.destination,
        group_size=request.group_size,
        start_date=request.start_date,
        end_date=request.end_date,
        hotel_rating=request.hotel_rating,
        meal_plan=request.meal_plan,
        tour_type=request.tour_type,
        budget=request.budget,
    )

    return {
        "request_id": request_id,
        "suggested_price": pricing["average_price"],
        "min_price": pricing["min_price"],
        "max_price": pricing["max_price"],
        "recommendation": pricing["recommendation"],
    }
