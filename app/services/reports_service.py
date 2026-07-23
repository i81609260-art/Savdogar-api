"""Reports and analytics business logic."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.company import Company, CompanyStatus
from app.models.site_visit import SiteVisit
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.schemas.reports import (
    DashboardStats,
    OverviewResponse,
    OverviewTopItem,
    OverviewTrendPoint,
    ReportsResponse,
    SalesDataPoint,
    StatusDistribution,
    SuperAdminStats,
    TopTourItem,
)

# Trend oralig'i sozlamalari: (necha bucket, bucket birligi, ko'rsatiladigan format).
# "all" alohida — birinchi ma'lumotdan hozirgacha oylab.
_RANGE_CONFIG = {
    "24h": ("hour", 24),
    "7d": ("day", 7),
    "28d": ("day", 28),
    "1y": ("month", 12),
}

_UZ_MONTHS = [
    "Yan", "Fev", "Mar", "Apr", "May", "Iyn",
    "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek",
]


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
        today = datetime.now(timezone.utc).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

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

        # Sort by ISO bucket key (e.g. "2025-01"), not by display period string
        return [v for _, v in sorted(buckets.items())]

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

    # ------------------------------------------------------------------ #
    # Dashboard "Overview" — real tashrif/foydalanuvchi/DAU/MAU + trend
    # ------------------------------------------------------------------ #

    @staticmethod
    def _aware(dt: datetime) -> datetime:
        """Naive (SQLite) sanani UTC deb belgilaydi; aware bo'lsa tegmaydi."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _add_months(d: datetime, delta: int) -> datetime:
        """Oy qo'shish/ayirish (kun 1-ga tenglashtiriladi)."""
        idx = (d.year * 12 + (d.month - 1)) + delta
        return datetime(idx // 12, idx % 12 + 1, 1, tzinfo=timezone.utc)

    def _bucket_starts(
        self, range_key: str, now: datetime, earliest: Optional[datetime]
    ) -> tuple[list[datetime], str]:
        """Trend bucket'larining boshlanish vaqtlari va birligi (hour|day|month)."""
        if range_key == "all":
            first = self._aware(earliest) if earliest else now
            months = (now.year - first.year) * 12 + (now.month - first.month)
            months = max(0, min(months, 35))  # ko'pi bilan 36 nuqta
            base = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            return [self._add_months(base, i - months) for i in range(months + 1)], "month"

        unit, count = _RANGE_CONFIG[range_key]
        if unit == "hour":
            base = now.replace(minute=0, second=0, microsecond=0)
            return [base - timedelta(hours=count - 1 - i) for i in range(count)], "hour"
        if unit == "day":
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return [base - timedelta(days=count - 1 - i) for i in range(count)], "day"
        # month
        base = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        return [self._add_months(base, i - (count - 1)) for i in range(count)], "month"

    @staticmethod
    def _bucket_key(dt: datetime, unit: str):
        if unit == "hour":
            return dt.replace(minute=0, second=0, microsecond=0)
        if unit == "day":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return (dt.year, dt.month)

    def _label(self, start: datetime, unit: str) -> str:
        if unit == "hour":
            return start.strftime("%H:00")
        if unit == "day":
            return f"{start.day} {_UZ_MONTHS[start.month - 1]}"
        return f"{_UZ_MONTHS[start.month - 1]} {str(start.year)[2:]}"

    async def _scalar(self, query) -> int:
        return (await self.db.execute(query)).scalar() or 0

    async def overview(
        self, company_id: Optional[int], range_key: str = "28d"
    ) -> OverviewResponse:
        """Superadmin (company_id=None) yoki bitta firma uchun umumiy ko'rinish.

        Barcha raqamlar real ma'lumotdan: tashriflar `site_visits`, DAU/MAU
        `last_active_at` + bronlar birlashmasidan, trend esa haqiqiy
        vaqt qatorlaridan hisoblanadi.
        """
        if range_key not in _RANGE_CONFIG and range_key != "all":
            range_key = "28d"
        now = datetime.now(timezone.utc)
        is_platform = company_id is None

        def vfilter(q):
            return q if is_platform else q.where(SiteVisit.company_id == company_id)

        def bfilter(q):
            return q if is_platform else q.where(Booking.company_id == company_id)

        # ---- Umumiy jami (lifetime) ----
        total_visits = await self._scalar(vfilter(select(func.count(SiteVisit.id))))
        total_bookings = await self._scalar(bfilter(select(func.count(Booking.id))))
        total_revenue = float(
            await self._scalar(
                bfilter(
                    select(func.coalesce(func.sum(Booking.total_price), 0)).where(
                        Booking.status == BookingStatus.CONFIRMED
                    )
                )
            )
        )

        if is_platform:
            total_users = await self._scalar(select(func.count(User.id)))
            total_companies = await self._scalar(select(func.count(Company.id)))
            pending_companies = await self._scalar(
                select(func.count(Company.id)).where(
                    Company.status == CompanyStatus.PENDING
                )
            )
            total_tours = await self._scalar(select(func.count(Tour.id)))
        else:
            total_users = await self._scalar(
                select(func.count(func.distinct(Booking.user_id))).where(
                    Booking.company_id == company_id
                )
            )
            total_companies = 0
            pending_companies = 0
            total_tours = await self._scalar(
                select(func.count(Tour.id)).where(Tour.company_id == company_id)
            )

        # ---- DAU / MAU (real faollik: last_active_at + bronlar) ----
        daily_active = await self._active_users(company_id, now - timedelta(hours=24), now)
        monthly_active = await self._active_users(company_id, now - timedelta(days=30), now)

        # ---- Trend qatori ----
        trends = await self._overview_trends(company_id, range_key, now)

        # ---- Reyting ----
        top = await self._overview_top(company_id)

        return OverviewResponse(
            scope="platform" if is_platform else "company",
            range=range_key,
            total_visits=total_visits,
            total_users=total_users,
            total_bookings=total_bookings,
            total_revenue=total_revenue,
            daily_active=daily_active,
            monthly_active=monthly_active,
            total_companies=total_companies,
            pending_companies=pending_companies,
            total_tours=total_tours,
            trends=trends,
            top=top,
        )

    async def _active_users(
        self, company_id: Optional[int], start: datetime, end: datetime
    ) -> int:
        """Oralig'da faol bo'lgan noyob foydalanuvchilar soni.

        Faol = shu vaqtda `last_active_at` yangilangan (tizimga kirgan xodim)
        YOKI bron qilgan mijoz. Ikkalasi birlashtiriladi.
        """
        active_q = select(User.id).where(User.last_active_at >= start)
        booked_q = select(Booking.user_id).where(Booking.created_at >= start)
        if company_id is not None:
            active_q = active_q.where(User.company_id == company_id)
            booked_q = booked_q.where(Booking.company_id == company_id)

        ids: set[int] = set()
        for row in (await self.db.execute(active_q)).scalars().all():
            ids.add(row)
        for row in (await self.db.execute(booked_q)).scalars().all():
            ids.add(row)
        return len(ids)

    async def _overview_trends(
        self, company_id: Optional[int], range_key: str, now: datetime
    ) -> List[OverviewTrendPoint]:
        is_platform = company_id is None

        # "all" uchun eng erta ma'lumot sanasini topamiz.
        earliest: Optional[datetime] = None
        if range_key == "all":
            vq = select(func.min(SiteVisit.created_at))
            bq = select(func.min(Booking.created_at))
            if not is_platform:
                vq = vq.where(SiteVisit.company_id == company_id)
                bq = bq.where(Booking.company_id == company_id)
            candidates = [
                (await self.db.execute(vq)).scalar(),
                (await self.db.execute(bq)).scalar(),
            ]
            if is_platform:
                candidates.append((await self.db.execute(select(func.min(User.created_at)))).scalar())
            valid = [self._aware(c) for c in candidates if c is not None]
            earliest = min(valid) if valid else now

        starts, unit = self._bucket_starts(range_key, now, earliest)
        window_start = starts[0]
        keys = [self._bucket_key(s, unit) for s in starts]
        # Har bir bucket kaliti -> indeks
        index = {k: i for i, k in enumerate(keys)}

        visits = [0] * len(starts)
        users = [0] * len(starts)
        bookings = [0] * len(starts)
        revenue = [0.0] * len(starts)

        # Tashriflar
        vq = select(SiteVisit.created_at).where(SiteVisit.created_at >= window_start)
        if not is_platform:
            vq = vq.where(SiteVisit.company_id == company_id)
        for (created,) in (await self.db.execute(vq)).all():
            k = self._bucket_key(self._aware(created), unit)
            if k in index:
                visits[index[k]] += 1

        # Bronlar (soni + daromad + firma uchun noyob mijoz)
        bq = select(
            Booking.created_at, Booking.user_id, Booking.total_price, Booking.status
        ).where(Booking.created_at >= window_start)
        if not is_platform:
            bq = bq.where(Booking.company_id == company_id)
        seen_users: list[set] = [set() for _ in starts]
        for created, uid, price, status in (await self.db.execute(bq)).all():
            k = self._bucket_key(self._aware(created), unit)
            if k not in index:
                continue
            i = index[k]
            bookings[i] += 1
            if status == BookingStatus.CONFIRMED:
                revenue[i] += float(price or 0)
            if not is_platform:
                seen_users[i].add(uid)

        # Foydalanuvchilar qatori: platforma → yangi ro'yxatdan o'tishlar;
        # firma → bucket ichida faol bo'lgan noyob mijozlar.
        if is_platform:
            uq = select(User.created_at).where(User.created_at >= window_start)
            for (created,) in (await self.db.execute(uq)).all():
                k = self._bucket_key(self._aware(created), unit)
                if k in index:
                    users[index[k]] += 1
        else:
            users = [len(s) for s in seen_users]

        return [
            OverviewTrendPoint(
                label=self._label(starts[i], unit),
                visits=visits[i],
                users=users[i],
                bookings=bookings[i],
                revenue=round(revenue[i], 2),
            )
            for i in range(len(starts))
        ]

    async def _overview_top(self, company_id: Optional[int]) -> List[OverviewTopItem]:
        """Platforma → top kompaniyalar; firma → top turlar (tasdiqlangan bron)."""
        if company_id is None:
            rows = (
                await self.db.execute(
                    select(
                        Company.id,
                        Company.name,
                        func.count(Booking.id).label("cnt"),
                        func.coalesce(func.sum(Booking.total_price), 0).label("rev"),
                    )
                    .join(Booking, Booking.company_id == Company.id)
                    .where(Booking.status == BookingStatus.CONFIRMED)
                    .group_by(Company.id)
                    .order_by(func.count(Booking.id).desc())
                    .limit(6)
                )
            ).all()
        else:
            rows = (
                await self.db.execute(
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
                    .limit(6)
                )
            ).all()
        return [
            OverviewTopItem(id=r[0], name=r[1] or "—", bookings=r[2], revenue=float(r[3]))
            for r in rows
        ]
