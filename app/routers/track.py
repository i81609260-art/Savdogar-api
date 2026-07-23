"""Ommaviy sahifa tashrifini yozish — tokensiz, dashboard metrikasi uchun.

Frontend ommaviy sayt ochilganda shu endpointga bitta so'rov yuboradi.
Auth talab qilinmaydi. Har qanday xato jim yutiladi — tashrif hisobi
foydalanuvchi tajribasini hech qachon buzmasligi kerak.
"""

import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.site_visit import SiteVisit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/track", tags=["Tracking"])


class VisitPayload(BaseModel):
    path: Optional[str] = None
    # Tashrif qaysi tur firma saytiga tegishli (slug orqali). Bo'sh — umumiy sahifa.
    company_slug: Optional[str] = None


def _visitor_key(request: Request) -> str:
    """IP + User-Agent'dan qisqa xesh — kunlik taxminiy noyoblik uchun.

    Shaxsni aniqlamaydi; faqat bir xil tashrif chini kamaytirishga yordam beradi.
    """
    ip = request.headers.get("x-forwarded-for", "") or (
        request.client.host if request.client else ""
    )
    ua = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{ip}|{ua}".encode()).hexdigest()[:32]


@router.post("/visit", summary="Sahifa tashrifini yozish")
async def track_visit(
    data: VisitPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bitta pageview yozadi. Doim {ok: true} qaytaradi (xato bo'lsa ham)."""
    try:
        company_id: Optional[int] = None
        if data.company_slug:
            company_id = (
                await db.execute(
                    select(Company.id).where(Company.slug == data.company_slug)
                )
            ).scalar_one_or_none()

        db.add(
            SiteVisit(
                company_id=company_id,
                path=(data.path or "")[:500] or None,
                visitor_key=_visitor_key(request),
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — tashrif yozuvi hech narsani sindirmasin
        logger.debug("Tashrif yozilmadi", exc_info=True)
        return {"ok": False}
    return {"ok": True}
