"""Tour requests CRM API — individual tur so'rovlarini boshqarish."""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services.pricing_calculator import PricingCalculator
from pydantic import BaseModel

router = APIRouter(prefix="/api/requests", tags=["Tour Requests"])


class LeadCreate(BaseModel):
    """Lead (Mijoz) ma'lumotlari."""
    full_name: str
    phone: str
    email: str


class TourRequestCreate(BaseModel):
    """Tur so'rovi yaratish."""
    lead_id: Optional[int] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    destination: Optional[str] = None
    group_type: Optional[str] = None
    group_size: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    hotel_rating: Optional[str] = None
    meal_plan: Optional[str] = None
    tour_type: Optional[str] = None
    budget: Optional[float] = None

    notes: Optional[str] = None


class TourRequestStatusUpdate(BaseModel):
    """So'rov statusini yangilash."""
    status: str  # Yangi, Taklif tayyorlanmoqda, Taklif yuborildi, Muzokara, Kelishildi, To'landi, Safarda, Yakunlandi


class TourRequestResponse(BaseModel):
    """So'rov javob."""
    id: int
    company_id: int
    lead_name: str
    lead_phone: str
    lead_email: str
    destination: Optional[str]
    group_type: Optional[str]
    group_size: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    hotel_rating: Optional[str]
    meal_plan: Optional[str]
    tour_type: Optional[str]
    budget: Optional[float]
    status: str
    notes: Optional[str]
    created_at: str
    updated_at: str


@router.post("", summary="Yangi tur so'rovi yaratish")
async def create_request(
    data: TourRequestCreate,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Yangi tur so'rovi yaratish (lead'dan yoki to'g'ridan-to'g'ri)."""
    from app.models.request import TourRequest

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    # Lead ma'lumotlarini olish
    lead_name = data.full_name or "Noma'lum"
    lead_phone = data.phone or ""
    lead_email = data.email or ""

    # So'rov yaratish
    request = TourRequest(
        company_id=current_user.company_id,
        lead_name=lead_name,
        lead_phone=lead_phone,
        lead_email=lead_email,
        destination=data.destination,
        group_type=data.group_type,
        group_size=data.group_size,
        start_date=data.start_date,
        end_date=data.end_date,
        hotel_rating=data.hotel_rating,
        meal_plan=data.meal_plan,
        tour_type=data.tour_type,
        budget=data.budget,
        status="Yangi",
        notes=data.notes,
    )

    db.add(request)
    await db.commit()
    await db.refresh(request)

    return {"id": request.id, "status": "Yangilandi"}


@router.get("", summary="Barcha so'rovlar")
async def list_requests(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> List[TourRequestResponse]:
    """Kompaniyaning barcha so'rovlari."""
    from app.models.request import TourRequest

    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniya topilmadi")

    result = await db.execute(
        select(TourRequest)
        .where(TourRequest.company_id == current_user.company_id)
        .order_by(TourRequest.created_at.desc())
    )
    requests = result.scalars().all()

    return [
        TourRequestResponse(
            id=req.id,
            company_id=req.company_id,
            lead_name=req.lead_name,
            lead_phone=req.lead_phone,
            lead_email=req.lead_email,
            destination=req.destination,
            group_type=req.group_type,
            group_size=req.group_size,
            start_date=req.start_date,
            end_date=req.end_date,
            hotel_rating=req.hotel_rating,
            meal_plan=req.meal_plan,
            tour_type=req.tour_type,
            budget=req.budget,
            status=req.status,
            notes=req.notes,
            created_at=req.created_at.isoformat(),
            updated_at=req.updated_at.isoformat(),
        )
        for req in requests
    ]


@router.get("/{request_id}", summary="So'rov detallari")
async def get_request(
    request_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> TourRequestResponse:
    """So'rov detallari."""
    from app.models.request import TourRequest

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

    return TourRequestResponse(
        id=request.id,
        company_id=request.company_id,
        lead_name=request.lead_name,
        lead_phone=request.lead_phone,
        lead_email=request.lead_email,
        destination=request.destination,
        group_type=request.group_type,
        group_size=request.group_size,
        start_date=request.start_date,
        end_date=request.end_date,
        hotel_rating=request.hotel_rating,
        meal_plan=request.meal_plan,
        tour_type=request.tour_type,
        budget=request.budget,
        status=request.status,
        notes=request.notes,
        created_at=request.created_at.isoformat(),
        updated_at=request.updated_at.isoformat(),
    )


@router.patch("/{request_id}/status", summary="So'rov statusini yangilash")
async def update_request_status(
    request_id: int,
    data: TourRequestStatusUpdate,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """So'rov statusini yangilash."""
    from app.models.request import TourRequest
    from app.routers.requests_ws import broadcast_request_status_update

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

    request.status = data.status
    await db.commit()

    # Broadcast status update via WebSocket
    await broadcast_request_status_update(
        request_id=request.id,
        company_id=request.company_id,
        new_status=request.status,
        updated_by_user_id=current_user.id,
    )

    return {"id": request.id, "status": request.status}


@router.patch("/{request_id}", summary="So'rovni yangilash")
async def update_request(
    request_id: int,
    data: TourRequestCreate,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """So'rov detalllarini yangilash."""
    from app.models.request import TourRequest

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

    # Yangilash
    if data.destination:
        request.destination = data.destination
    if data.group_type:
        request.group_type = data.group_type
    if data.group_size:
        request.group_size = data.group_size
    if data.start_date:
        request.start_date = data.start_date
    if data.end_date:
        request.end_date = data.end_date
    if data.hotel_rating:
        request.hotel_rating = data.hotel_rating
    if data.meal_plan:
        request.meal_plan = data.meal_plan
    if data.tour_type:
        request.tour_type = data.tour_type
    if data.budget:
        request.budget = data.budget
    if data.notes:
        request.notes = data.notes

    await db.commit()

    return {"id": request.id, "updated": True}


@router.post("/calculate-price", summary="Tur narxini hisoblash")
async def calculate_tour_price(
    destination: Optional[str] = None,
    group_size: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hotel_rating: Optional[str] = None,
    meal_plan: Optional[str] = None,
    tour_type: Optional[str] = None,
    budget: Optional[float] = None,
) -> dict:
    """Tur so'roviga asosan narxni hisoblash."""
    return PricingCalculator.calculate_price(
        destination=destination,
        group_size=group_size,
        start_date=start_date,
        end_date=end_date,
        hotel_rating=hotel_rating,
        meal_plan=meal_plan,
        tour_type=tour_type,
        budget=budget,
    )
