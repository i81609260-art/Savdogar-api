"""Excel/PDF export endpoints for CRM customers, tours, and reports."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.crm_service import CRMService
from app.services.export_service import (
    XLSX_MEDIA_TYPE,
    rows_to_excel,
    rows_to_pdf,
)
from app.services.reports_service import ReportsService

router = APIRouter(prefix="/api/exports", tags=["Exports"])

_ADMIN = role_required(UserRole.ADMIN, UserRole.OPERATOR)


def _download(fmt: str, base_name: str, title: str, headers, rows) -> Response:
    """Render rows into the requested format and wrap as a file download."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if fmt == "pdf":
        content = rows_to_pdf(title, headers, rows)
        media_type, ext = "application/pdf", "pdf"
    else:
        content = rows_to_excel(title, headers, rows)
        media_type, ext = XLSX_MEDIA_TYPE, "xlsx"
    filename = f"{base_name}_{stamp}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/customers",
    summary="Mijozlarni Excel/PDF yuklab olish",
    dependencies=[Depends(_ADMIN)],
)
async def export_customers(
    format: str = Query("excel", pattern="^(excel|pdf)$"),
    current_user: User = Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export all company customers with their CRM stats."""
    service = CRMService(db)
    result = await service.list_customers(current_user, page=1, page_size=1_000_000)
    headers = [
        "ID", "F.I.Sh", "Telefon", "Email", "Bronlar",
        "Tasdiqlangan", "Jami xarajat", "Segment", "Oxirgi bron",
    ]
    rows = [
        [
            c.id, c.full_name, c.phone or "", c.email, c.total_bookings,
            c.confirmed_bookings, c.total_spent, c.segment,
            c.last_booking_at.strftime("%Y-%m-%d") if c.last_booking_at else "",
        ]
        for c in result.items
    ]
    return _download(format, "mijozlar", "Mijozlar royxati", headers, rows)


@router.get(
    "/tours",
    summary="Tur paketlarni Excel/PDF yuklab olish",
    dependencies=[Depends(_ADMIN)],
)
async def export_tours(
    format: str = Query("excel", pattern="^(excel|pdf)$"),
    current_user: User = Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export the company's tour packages."""
    rows: list = []
    if current_user.company_id:
        result = await db.execute(
            select(Tour)
            .where(Tour.company_id == current_user.company_id)
            .order_by(Tour.created_at.desc())
        )
        tours = result.scalars().all()
        rows = [
            [
                t.id, t.title, t.city, t.country, t.price, t.currency,
                t.duration_days, str(t.start_date), str(t.end_date),
                t.available_slots, "Ha" if t.is_active else "Yo'q",
            ]
            for t in tours
        ]
    headers = [
        "ID", "Nomi", "Shahar", "Davlat", "Narx", "Valyuta", "Kunlar",
        "Boshlanish", "Tugash", "Bosh joylar", "Faol",
    ]
    return _download(format, "tur_paketlar", "Tur paketlar", headers, rows)


@router.get(
    "/reports",
    summary="Umumiy hisobotni Excel/PDF yuklab olish",
    dependencies=[Depends(_ADMIN)],
)
async def export_reports(
    format: str = Query("excel", pattern="^(excel|pdf)$"),
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    current_user: User = Depends(_ADMIN),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export sales report (revenue and bookings by period)."""
    service = ReportsService(db)
    data = await service.get_reports(current_user, period)
    headers = ["Davr", "Bronlar soni", "Daromad"]
    rows = [[p.period, p.bookings_count, p.revenue] for p in data.sales]
    # Trailing summary row.
    rows.append([
        "JAMI",
        sum(p.bookings_count for p in data.sales),
        sum(p.revenue for p in data.sales),
    ])
    return _download(format, "hisobot", "Sotuv hisoboti", headers, rows)
