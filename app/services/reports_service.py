"""Reports and analytics business logic."""

from datetime import date, datetime, timedelta, timezone
from typing import List

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.reports import (
    DashboardStats,
    ReportsResponse,
    SalesDataPoint,
    StatusDistribution,
    SuperAdminStats,
    TopTourItem,
)


class ReportsService:
    """Generate sales reports and dashboard statistics."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_reports(
        self, user: User, period: str = "monthly"
    ) -> ReportsResponse:
        """Build full reports for admin dashboard."""
        if not user.company_id:
            raise HTTPException(status_code=403, detail="Kompaniyaga biriktirilmagansiz")

        company_id = user.company_id
        sales = await self._sales_data(company_id, period)
        top_tours = await self._top_tours(company_id)
        status_dist = await self._status_distribution(company_id)
        dashboard = await self._dashboard_stats(company_id)

        return ReportsResponse(
            sales=sales,
            top_tours=top_tours,
            status_distribution=status_dist,
            dashboard=dashboard,
        )

    async def _dashboard_stats(self, company_id: int) -> DashboardStats:
        """Calculate dashboard KPIs."""
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        today_bookings_q = await self.db.execute(
            select(func.count(Booking.id)).where(
                Booking.company_id == company_id,
                Booking.created_at >= today_start,
            )
        )
        today_bookings = today_bookings_q.scalar() or 0

        today_revenue_q = await self.db.execute(
            select(func.coalesce(func.sum(Booking.total_price), 0)).where(
                Booking.company_id == company_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.created_at >= today_start,
            )
        )
        today_revenue = float(today_revenue_q.scalar() or 0)

        active_tours_q = await self.db.execute(
            select(func.count(Tour.id)).where(
                Tour.company_id == company_id,
                Tour.is_active == True,  # noqa: E712
            )
        )
        active_tours = active_tours_q.scalar() or 0

        customers_q = await self.db.execute(
            select(func.count(func.distinct(Booking.user_id))).where(
                Booking.company_id == company_id
            )
        )
        total_customers = customers_q.scalar() or 0

        pending_q = await self.db.execute(
            select(func.count(Booking.id)).where(
                Booking.company_id == company_id,
                Booking.status == BookingStatus.PENDING,
            )
        )
        pending_bookings = pending_q.scalar() or 0

        return DashboardStats(
            today_bookings=today_bookings,
            today_revenue=today_revenue,
            active_tours=active_tours,
            total_customers=total_customers,
            pending_bookings=pending_bookings,
        )

    async def _sales_data(self, company_id: int, period: str) -> List[SalesDataPoint]:
        """Aggregate sales by day/week/month."""
        now = datetime.now(timezone.utc)
        if period == "daily":
            days, fmt = 7, "%d.%m"
        elif period == "weekly":
            days, fmt = 28, "Hafta %W"
        else:
            days, fmt = 180, "%m.%Y"

        start = now - timedelta(days=days)
        result = await self.db.execute(
            select(Booking).where(
                Booking.company_id == company_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.created_at >= start,
            )
        )
        bookings = result.scalars().all()

        buckets: dict[str, SalesDataPoint] = {}
        for b in bookings:
            if period == "weekly":
                key = b.created_at.strftime("%Y-W%W")
            elif period == "monthly":
                key = b.created_at.strftime("%Y-%m")
            else:
                key = b.created_at.strftime("%Y-%m-%d")

            if key not in buckets:
                buckets[key] = SalesDataPoint(
                    period=b.created_at.strftime(fmt),
                    revenue=0,
                    bookings_count=0,
                )
            buckets[key].revenue += b.total_price
            buckets[key].bookings_count += 1

        return sorted(buckets.values(), key=lambda x: x.period)

    async def _top_tours(self, company_id: int, limit: int = 5) -> List[TopTourItem]:
        """Top selling tours by confirmed bookings."""
        result = await self.db.execute(
            select(
                Tour.id,
                Tour.title,
                func.count(Booking.id).label("cnt"),
                func.coalesce(func.sum(Booking.total_price), 0).label("rev"),
            )
            .join(Booking, Booking.tour_id == Tour.id)
            .where(
                Tour.company_id == company_id,
                Booking.status == BookingStatus.CONFIRMED,
            )
            .group_by(Tour.id)
            .order_by(func.count(Booking.id).desc())
            .limit(limit)
        )
        rows = result.all()
        return [
            TopTourItem(
                tour_id=r.id,
                tour_title=r.title,
                bookings_count=r.cnt,
                revenue=float(r.rev),
            )
            for r in rows
        ]

    async def _status_distribution(self, company_id: int) -> StatusDistribution:
        """Booking status counts for pie chart."""
        dist = StatusDistribution(pending=0, confirmed=0, cancelled=0)
        for status in BookingStatus:
            q = await self.db.execute(
                select(func.count(Booking.id)).where(
                    Booking.company_id == company_id,
                    Booking.status == status,
                )
            )
            count = q.scalar() or 0
            setattr(dist, status.value, count)
        return dist

    async def superadmin_stats(self) -> SuperAdminStats:
        """Platform-wide statistics for superadmin."""
        from app.models.company import Company, CompanyStatus

        companies = (await self.db.execute(select(func.count(Company.id)))).scalar() or 0
        pending = (
            await self.db.execute(
                select(func.count(Company.id)).where(
                    Company.status == CompanyStatus.PENDING
                )
            )
        ).scalar() or 0
        approved = (
            await self.db.execute(
                select(func.count(Company.id)).where(
                    Company.status == CompanyStatus.APPROVED
                )
            )
        ).scalar() or 0
        users = (await self.db.execute(select(func.count(User.id)))).scalar() or 0
        tours = (await self.db.execute(select(func.count(Tour.id)))).scalar() or 0
        bookings = (await self.db.execute(select(func.count(Booking.id)))).scalar() or 0
        revenue = (
            await self.db.execute(
                select(func.coalesce(func.sum(Booking.total_price), 0)).where(
                    Booking.status == BookingStatus.CONFIRMED
                )
            )
        ).scalar() or 0

        return SuperAdminStats(
            total_companies=companies,
            pending_companies=pending,
            approved_companies=approved,
            total_users=users,
            total_tours=tours,
            total_bookings=bookings,
            total_revenue=float(revenue),
        )
