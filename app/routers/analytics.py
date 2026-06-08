"""Analytics and reporting for admin dashboard."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from pydantic import BaseModel

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


class DashboardStats(BaseModel):
    """Dashboard statistics."""

    total_requests: int
    pending_requests: int
    completed_requests: int
    total_revenue: float
    average_request_value: float
    request_conversion_rate: float
    top_destinations: list
    request_trends: list


@router.get("/dashboard", summary="Dashboard statistikasi")
async def get_dashboard_stats(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get dashboard statistics for company."""
    from app.models.request import TourRequest
    from app.models.booking import Booking

    if not current_user.company_id:
        return {"error": "Kompaniya topilmadi"}

    # Total requests
    total_requests_result = await db.execute(
        select(func.count(TourRequest.id)).where(
            TourRequest.company_id == current_user.company_id
        )
    )
    total_requests = total_requests_result.scalar() or 0

    # Pending requests
    pending_result = await db.execute(
        select(func.count(TourRequest.id)).where(
            and_(
                TourRequest.company_id == current_user.company_id,
                TourRequest.status == "Yangi",
            )
        )
    )
    pending_requests = pending_result.scalar() or 0

    # Completed requests
    completed_result = await db.execute(
        select(func.count(TourRequest.id)).where(
            and_(
                TourRequest.company_id == current_user.company_id,
                TourRequest.status.in_(["To'landi", "Yakunlandi"]),
            )
        )
    )
    completed_requests = completed_result.scalar() or 0

    # Total revenue from bookings
    revenue_result = await db.execute(
        select(func.sum(Booking.total_price)).where(
            and_(
                Booking.company_id == current_user.company_id,
                Booking.status.in_(["completed", "confirmed"]),
            )
        )
    )
    total_revenue = revenue_result.scalar() or 0

    # Top destinations
    destinations_result = await db.execute(
        select(
            TourRequest.destination,
            func.count(TourRequest.id).label("count"),
        )
        .where(TourRequest.company_id == current_user.company_id)
        .group_by(TourRequest.destination)
        .order_by(func.count(TourRequest.id).desc())
        .limit(5)
    )
    top_destinations = [
        {"destination": row[0], "count": row[1]} for row in destinations_result
    ]

    # Request trends (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    trends_result = await db.execute(
        select(
            func.date(TourRequest.created_at).label("date"),
            func.count(TourRequest.id).label("count"),
        )
        .where(
            and_(
                TourRequest.company_id == current_user.company_id,
                TourRequest.created_at >= seven_days_ago,
            )
        )
        .group_by(func.date(TourRequest.created_at))
        .order_by(func.date(TourRequest.created_at))
    )
    request_trends = [
        {"date": str(row[0]), "count": row[1]} for row in trends_result
    ]

    conversion_rate = (
        (completed_requests / total_requests * 100) if total_requests > 0 else 0
    )
    average_request_value = (
        (total_revenue / completed_requests) if completed_requests > 0 else 0
    )

    return {
        "total_requests": total_requests,
        "pending_requests": pending_requests,
        "completed_requests": completed_requests,
        "total_revenue": total_revenue,
        "average_request_value": round(average_request_value, 2),
        "request_conversion_rate": round(conversion_rate, 2),
        "top_destinations": top_destinations,
        "request_trends": request_trends,
    }


@router.get("/requests-by-status", summary="Statusga asosan so'rovlar")
async def get_requests_by_status(
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get request counts by status."""
    from app.models.request import TourRequest

    result = await db.execute(
        select(TourRequest.status, func.count(TourRequest.id).label("count"))
        .where(TourRequest.company_id == current_user.company_id)
        .group_by(TourRequest.status)
    )
    rows = result.all()

    return {
        status: count for status, count in rows
    }


@router.get("/revenue-trend", summary="Daromad tendentsiyasi")
async def get_revenue_trend(
    days: int = 30,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list:
    """Get revenue trend over time."""
    from app.models.booking import Booking

    start_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(Booking.created_at).label("date"),
            func.sum(Booking.total_price).label("revenue"),
        )
        .where(
            and_(
                Booking.company_id == current_user.company_id,
                Booking.created_at >= start_date,
            )
        )
        .group_by(func.date(Booking.created_at))
        .order_by(func.date(Booking.created_at))
    )
    rows = result.all()

    return [
        {"date": str(row[0]), "revenue": float(row[1] or 0)} for row in rows
    ]
