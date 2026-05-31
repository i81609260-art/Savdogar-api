"""Tour group endpoints — public reads + admin CRUD."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.booking import Booking, BookingStatus
from app.models.tour import Tour
from app.models.tour_group import TourGroup
from app.models.user import User, UserRole
from app.schemas.tour_group import (
    TourGroupCreate,
    TourGroupResponse,
    TourGroupUpdate,
    UpcomingGroupResponse,
)

public_router = APIRouter(prefix="/api", tags=["Tour Groups"])
admin_router = APIRouter(prefix="/api/admin", tags=["Admin – Tour Groups"])


# ── Public ────────────────────────────────────────────────────────────────────

@public_router.get(
    "/companies/{company_id}/upcoming-groups",
    response_model=list[UpcomingGroupResponse],
    summary="Kompaniyaning yaqin guruhlar/reyslar (public)",
)
async def upcoming_groups(
    company_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[UpcomingGroupResponse]:
    """Return upcoming active groups sorted by departure_date (for the public company page)."""
    today = date.today()
    result = await db.execute(
        select(TourGroup, Tour.title, Tour.city)
        .join(Tour, TourGroup.tour_id == Tour.id)
        .where(
            TourGroup.company_id == company_id,
            TourGroup.is_active.is_(True),
            TourGroup.departure_date >= today,
        )
        .order_by(TourGroup.departure_date)
        .limit(limit)
    )
    rows = result.all()
    out = []
    for group, title, city in rows:
        item = UpcomingGroupResponse(
            **TourGroupResponse.model_validate(group).model_dump(),
            tour_title=title,
            tour_destination=city,
        )
        out.append(item)
    return out


@public_router.get(
    "/tours/{tour_id}/groups",
    response_model=list[TourGroupResponse],
    summary="Programma guruhlar/reyslar ro'yxati (public)",
)
async def tour_groups(
    tour_id: int,
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by departure month"),
    year: Optional[int] = Query(None, ge=2024, description="Filter by departure year"),
    db: AsyncSession = Depends(get_db),
) -> list[TourGroupResponse]:
    """List active upcoming groups for a tour program, optionally filtered by month/year."""
    today = date.today()
    q = (
        select(TourGroup)
        .where(
            TourGroup.tour_id == tour_id,
            TourGroup.is_active.is_(True),
            TourGroup.departure_date >= today,
        )
        .order_by(TourGroup.departure_date)
    )
    if month:
        from sqlalchemy import extract
        q = q.where(extract("month", TourGroup.departure_date) == month)
    if year:
        from sqlalchemy import extract
        q = q.where(extract("year", TourGroup.departure_date) == year)

    result = await db.execute(q)
    return [TourGroupResponse.model_validate(g) for g in result.scalars().all()]


# ── Admin CRUD ─────────────────────────────────────────────────────────────────

@admin_router.post(
    "/tours/{tour_id}/groups",
    response_model=TourGroupResponse,
    summary="Guruh/reys qo'shish (admin)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def create_group(
    tour_id: int,
    data: TourGroupCreate,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> TourGroupResponse:
    tour_result = await db.execute(select(Tour).where(Tour.id == tour_id))
    tour = tour_result.scalar_one_or_none()
    if not tour:
        raise HTTPException(status_code=404, detail="Tur topilmadi")
    if tour.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    group = TourGroup(
        tour_id=tour_id,
        company_id=tour.company_id,
        **data.model_dump(),
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return TourGroupResponse.model_validate(group)


@admin_router.put(
    "/groups/{group_id}",
    response_model=TourGroupResponse,
    summary="Guruhni tahrirlash (admin)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def update_group(
    group_id: int,
    data: TourGroupUpdate,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> TourGroupResponse:
    result = await db.execute(select(TourGroup).where(TourGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Guruh topilmadi")
    if group.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(group, field, value)
    await db.commit()
    await db.refresh(group)
    return TourGroupResponse.model_validate(group)


@admin_router.delete(
    "/groups/{group_id}",
    status_code=204,
    summary="Guruhni o'chirish (admin)",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def delete_group(
    group_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(TourGroup).where(TourGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Guruh topilmadi")
    if group.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    await db.delete(group)
    await db.commit()


# ── Booking a group slot ───────────────────────────────────────────────────────

@public_router.post(
    "/groups/{group_id}/book",
    response_model=dict,
    summary="Guruhga joy band qilish",
)
async def book_group(
    group_id: int,
    guests_count: int = Query(1, ge=1, le=10),
    notes: Optional[str] = None,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(TourGroup).where(TourGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group or not group.is_active:
        raise HTTPException(status_code=404, detail="Guruh topilmadi")
    if group.available_slots < guests_count:
        raise HTTPException(status_code=400, detail="Yetarli joy yo'q")

    booking = Booking(
        user_id=current_user.id,
        tour_id=group.tour_id,
        group_id=group.id,
        company_id=group.company_id,
        guests_count=guests_count,
        total_price=group.price * guests_count,
        notes=notes,
        status=BookingStatus.PENDING,
    )
    group.booked_slots += guests_count
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return {"booking_id": booking.id, "status": booking.status, "total_price": booking.total_price}
