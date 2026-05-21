"""Reports and dashboard API routes."""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from app.schemas.booking import BookingResponse
from app.schemas.reports import DashboardStats, ReportsResponse
from app.services.booking_service import BookingService
from app.services.reports_service import ReportsService

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.get(
    "",
    response_model=ReportsResponse,
    summary="Hisobotlar",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def get_reports(
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> ReportsResponse:
    """Sales reports, top tours, status distribution."""
    service = ReportsService(db)
    return await service.get_reports(current_user, period)


@router.get(
    "/dashboard",
    response_model=DashboardStats,
    summary="Dashboard KPI",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def dashboard_stats(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> DashboardStats:
    """Quick dashboard statistics."""
    service = ReportsService(db)
    reports = await service.get_reports(current_user)
    return reports.dashboard


@router.get(
    "/recent-bookings",
    response_model=List[BookingResponse],
    summary="Oxirgi bronlar",
    dependencies=[Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR))],
)
async def recent_bookings(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> List[BookingResponse]:
    """Last 5 bookings for dashboard table."""
    service = BookingService(db)
    if not current_user.company_id:
        return []
    return await service.recent_bookings(current_user.company_id)
