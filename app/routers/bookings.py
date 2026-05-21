"""Bookings API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.booking import BookingStatus
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingResponse, BookingStatusUpdate
from app.services.booking_service import BookingService
from app.utils.pagination import PaginatedResponse

router = APIRouter(prefix="/api/bookings", tags=["Bookings"])


def _get_sio(request: Request):
    """Get Socket.io server from app state."""
    return getattr(request.app.state, "sio", None)


@router.post(
    "",
    response_model=BookingResponse,
    summary="Bron qilish",
    dependencies=[Depends(role_required(UserRole.USER))],
)
async def create_booking(
    data: BookingCreate,
    request: Request,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """User creates a pending booking."""
    service = BookingService(db, _get_sio(request))
    return await service.create_booking(current_user, data)


@router.get("", response_model=PaginatedResponse[BookingResponse], summary="Bronlar ro'yxati")
async def list_bookings(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[BookingStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[BookingResponse]:
    """List bookings based on user role."""
    service = BookingService(db, _get_sio(request))
    return await service.list_bookings(
        current_user, page=page, page_size=page_size, status_filter=status
    )


@router.get("/{booking_id}", response_model=BookingResponse, summary="Bron tafsiloti")
async def get_booking(
    booking_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Get single booking."""
    service = BookingService(db, _get_sio(request))
    return await service.get_booking(current_user, booking_id)


@router.patch(
    "/{booking_id}/status",
    response_model=BookingResponse,
    summary="Bron statusini o'zgartirish",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.SUPERADMIN))],
)
async def update_booking_status(
    booking_id: int,
    data: BookingStatusUpdate,
    request: Request,
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
) -> BookingResponse:
    """Admin confirms or cancels booking."""
    service = BookingService(db, _get_sio(request))
    return await service.update_status(current_user, booking_id, data)
