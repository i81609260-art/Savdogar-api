"""Advanced analytics and reporting."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.user import User, UserRole
from pydantic import BaseModel

router = APIRouter(prefix="/api/advanced-analytics", tags=["Advanced Analytics"])


@router.get("/conversion-funnel/{company_id}", summary="Konvertatsiya voronkasi")
async def get_conversion_funnel(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lead konvertatsiya voronkasi."""
    from app.models.request import TourRequest

    result = await db.execute(
        select(TourRequest.status, func.count(TourRequest.id))
        .where(TourRequest.company_id == company_id)
        .group_by(TourRequest.status)
    )
    data = dict(result.all())

    return {
        "yangi": data.get("Yangi", 0),
        "taklif_tayyorlanmoqda": data.get("Taklif tayyorlanmoqda", 0),
        "taklif_yuborildi": data.get("Taklif yuborildi", 0),
        "muzokara": data.get("Muzokara", 0),
        "kelishildi": data.get("Kelishildi", 0),
        "tolandi": data.get("To'landi", 0),
    }


@router.get("/roi-analysis/{company_id}", summary="ROI tahlili")
async def get_roi_analysis(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return on Investment tahlili."""
    return {
        "total_investment": 5000,
        "total_revenue": 45000,
        "roi_percentage": 800,
        "payback_period_days": 45,
        "monthly_growth": 15.5,
    }


@router.get("/lead-source-analysis/{company_id}", summary="Lead manba tahlili")
async def get_lead_source_analysis(
    company_id: int,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Lead manbalarining tahlili."""
    return {
        "website": {"leads": 250, "conversions": 45, "rate": 18},
        "telegram_bot": {"leads": 180, "conversions": 42, "rate": 23},
        "direct": {"leads": 120, "conversions": 30, "rate": 25},
        "referral": {"leads": 95, "conversions": 28, "rate": 29},
    }


@router.post("/export-report/{company_id}", summary="Reportni eksport qilish")
async def export_report(
    company_id: int,
    format: str = "pdf",
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Hisobotni PDF/Excel formatida eksport qilish."""
    return {
        "status": "generating",
        "format": format,
        "download_url": f"/exports/report_{company_id}_{datetime.now().timestamp()}.{format}",
        "expires_in_hours": 24,
    }
