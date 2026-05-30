"""Tour packages API routes."""

import os
import uuid
from datetime import date
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.schemas.tour import TourCreate, TourResponse, TourUpdate
from app.services.tour_service import TourService
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/api/tours", tags=["Tours"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[TourResponse], summary="Tur ro'yxati")
async def list_tours(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    city: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    start_date: Optional[date] = None,
    min_slots: Optional[int] = None,
    search: Optional[str] = None,
    company_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TourResponse]:
    """Public tour catalog with filters."""
    service = TourService(db)
    return await service.list_tours(
        page=page,
        page_size=page_size,
        city=city,
        min_price=min_price,
        max_price=max_price,
        start_date=start_date,
        min_slots=min_slots,
        search=search,
        company_id=company_id,
    )


@router.get("/{tour_id}", response_model=TourResponse, summary="Tur tafsilotlari")
async def get_tour(
    tour_id: int,
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Get tour details."""
    service = TourService(db)
    return await service.get_tour(tour_id)


@router.post(
    "",
    response_model=TourResponse,
    summary="Tur yaratish",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def create_tour(
    data: TourCreate,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Admin creates a new tour package."""
    service = TourService(db)
    return await service.create_tour(current_user, data)


@router.patch(
    "/{tour_id}",
    response_model=TourResponse,
    summary="Tur tahrirlash",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def update_tour(
    tour_id: int,
    data: TourUpdate,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Admin updates tour package."""
    service = TourService(db)
    return await service.update_tour(current_user, tour_id, data)


@router.delete(
    "/{tour_id}",
    summary="Tur o'chirish",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def delete_tour(
    tour_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Admin soft-deletes tour."""
    service = TourService(db)
    return await service.delete_tour(current_user, tour_id)


@router.post(
    "/{tour_id}/image",
    response_model=TourResponse,
    summary="Tur rasmi yuklash",
    dependencies=[Depends(role_required(UserRole.ADMIN))],
)
async def upload_tour_image(
    tour_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> TourResponse:
    """Upload tour cover image."""
    os.makedirs(settings.upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        content = await file.read()
        await f.write(content)

    image_url = f"/uploads/{filename}"
    service = TourService(db)
    return await service.upload_image(current_user, tour_id, image_url)
