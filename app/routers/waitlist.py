"""Waitlist API — to'la turlar uchun navbat."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.services.waitlist_service import WaitlistService

router = APIRouter(prefix="/api/tours", tags=["Waitlist"])


def _sio(request: Request):
    return getattr(request.app.state, "sio", None)


@router.post(
    "/{tour_id}/waitlist",
    summary="Navbatga yozilish",
    dependencies=[Depends(role_required(UserRole.USER))],
)
async def join_waitlist(
    tour_id: int,
    request: Request,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WaitlistService(db, _sio(request)).join(current_user, tour_id)


@router.delete(
    "/{tour_id}/waitlist",
    summary="Navbatdan chiqish",
    dependencies=[Depends(role_required(UserRole.USER))],
)
async def leave_waitlist(
    tour_id: int,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WaitlistService(db).leave(current_user, tour_id)


@router.get(
    "/{tour_id}/waitlist/status",
    summary="Navbat holati",
    dependencies=[Depends(role_required(UserRole.USER))],
)
async def waitlist_status(
    tour_id: int,
    current_user: User = Depends(role_required(UserRole.USER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WaitlistService(db).status(current_user, tour_id)
