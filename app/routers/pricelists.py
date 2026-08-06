"""Price-list yuklash va yig'ilgan narxlarni ko'rish.

Operatorlar narxni Excel, PDF yoki Telegram xabari ko'rinishida tarqatadi.
Bu router shu fayllarni qabul qiladi, tahlil qiladi va natijani turagentning
o'z narx bazasiga yozadi.

Har bir so'rov `current_user.company_id` bo'yicha filtrlanadi — bir
turagentning narxi boshqasiga hech qanday yo'l bilan ko'rinmaydi.
"""

# DIQQAT: bu faylda `from __future__ import annotations` ISHLATILMAYDI.
# U barcha annotatsiyalarni matnga aylantiradi va FastAPI `UploadFile` ni
# Pydantic maydoni deb o'qib, "Invalid args for response field" xatosi
# bilan yiqiladi.

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.role_guard import role_required
from app.models.tour_offer import OfferSource, TourOffer
from app.models.tour_operator import TourOperator
from app.models.user import User, UserRole
from app.services.offer_service import list_offers, save_offers
from app.services.pricelist_parser import parse_pricelist, parse_pricelist_async
from app.utils.limiter import limiter

router = APIRouter(prefix="/api/pricelists", tags=["Price-list"])
offers_router = APIRouter(prefix="/api/offers", tags=["Takliflar"])

settings = get_settings()
_STAFF = role_required(UserRole.ADMIN, UserRole.OPERATOR)

# Price-list — jadval yoki matn, rasm emas. 10 MB dan katta price-list
# amalda uchramaydi; cheklov diskni himoya qiladi.
MAX_SIZE = 10 * 1024 * 1024


class OfferOut(BaseModel):
    id: Optional[int] = None
    hotel_name: str
    city: Optional[str] = None
    country: Optional[str] = None
    star: Optional[str] = None
    board: Optional[str] = None
    room: Optional[str] = None
    nights: Optional[int] = None
    price_gross: Optional[float] = None
    price_net: Optional[float] = None
    agent_margin: Optional[float] = None
    currency: str = "USD"
    operator_name: Optional[str] = None
    source: str = OfferSource.PRICELIST
    confidence: Optional[float] = None
    fetched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_fresh: bool = True
    is_saved: bool = False


class UploadResult(BaseModel):
    """Tahlil natijasi — nima o'qildi, nima o'qilmadi.

    `skipped` va `warnings` ataylab qaytariladi: "142 tadan 8 tasi
    o'qilmadi" agentga ko'rsatilishi kerak. Jim yutilgan qator —
    yo'qolgan narx demakdir.
    """

    found: int
    saved: int
    skipped: int
    total_rows: int
    warnings: list[str] = []
    offers_preview: list[OfferOut] = []


def _offer_out(offer: TourOffer, now: datetime) -> OfferOut:
    return OfferOut(
        id=offer.id,
        hotel_name=offer.hotel_name,
        city=offer.city,
        country=offer.country,
        star=offer.star,
        board=offer.board,
        room=offer.room,
        nights=offer.nights,
        price_gross=offer.price_gross,
        price_net=offer.price_net,
        agent_margin=offer.agent_margin,
        currency=offer.currency,
        operator_name=offer.operator_name,
        source=offer.source,
        confidence=offer.confidence,
        fetched_at=offer.fetched_at,
        expires_at=offer.expires_at,
        is_fresh=offer.is_fresh(now),
        is_saved=bool(offer.is_saved),
    )


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")
    return user.company_id


# --------------------------------------------------------------------------
# Yuklash
# --------------------------------------------------------------------------
@router.post("/upload", summary="Price-list yuklash")
@limiter.limit("20/minute")
async def upload_pricelist(
    request: Request,
    file: UploadFile = File(...),
    operator_id: Optional[int] = Form(default=None),
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
) -> UploadResult:
    """Excel / CSV / PDF / matn price-list'ni tahlil qilib bazaga yozadi."""
    cid = _company_id(current_user)

    # Hajm o'qishdan OLDIN emas, o'qish DAVOMIDA tekshiriladi: `UploadFile`
    # da ishonchli `size` yo'q, sarlavhaga esa ishonib bo'lmaydi.
    content = await file.read(MAX_SIZE + 1)
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Fayl juda katta (eng ko'pi {MAX_SIZE // 1024 // 1024} MB)",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Fayl bo'sh")

    operator_name = None
    if operator_id is not None:
        # Operator shu turagentga ko'rinadimi — katalog yoki o'ziniki.
        operator = (
            await db.execute(
                select(TourOperator).where(
                    TourOperator.id == operator_id,
                    (TourOperator.company_id.is_(None))
                    | (TourOperator.company_id == cid),
                )
            )
        ).scalar_one_or_none()
        if operator is None:
            raise HTTPException(status_code=404, detail="Operator topilmadi")
        operator_name = operator.name

    # Asinxron variant rasmni ham qo'llab-quvvatlaydi; qolgan formatlar
    # uchun farq yo'q.
    result = await parse_pricelist_async(
        content, filename=file.filename or "", content_type=file.content_type or ""
    )

    saved = await save_offers(
        db,
        company_id=cid,
        offers=result.offers,
        source=OfferSource.PRICELIST,
        operator_id=operator_id,
        operator_name=operator_name,
    )

    now = datetime.now(saved[0].expires_at.tzinfo) if saved else datetime.now()
    return UploadResult(
        found=len(result.offers),
        saved=len(saved),
        skipped=result.skipped,
        total_rows=result.total_rows,
        warnings=result.warnings,
        offers_preview=[_offer_out(o, now) for o in saved[:10]],
    )


@router.post("/paste", summary="Matnli price-list (Telegram xabari)")
@limiter.limit("20/minute")
async def paste_pricelist(
    request: Request,
    text: str = Form(...),
    operator_id: Optional[int] = Form(default=None),
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
) -> UploadResult:
    """Telegram'dan nusxa olingan matnni tahlil qiladi.

    Fayl yuklashdan ko'ra tez: agent xabarni nusxalab tashlaydi. Bot
    ishlovchisi ham keyinchalik AYNAN shu yo'ldan foydalanadi.
    """
    cid = _company_id(current_user)
    if not (text or "").strip():
        raise HTTPException(status_code=400, detail="Matn bo'sh")

    result = parse_pricelist(text)
    saved = await save_offers(
        db,
        company_id=cid,
        offers=result.offers,
        source=OfferSource.PRICELIST,
        operator_id=operator_id,
    )
    now = datetime.now(saved[0].expires_at.tzinfo) if saved else datetime.now()
    return UploadResult(
        found=len(result.offers),
        saved=len(saved),
        skipped=result.skipped,
        total_rows=result.total_rows,
        warnings=result.warnings,
        offers_preview=[_offer_out(o, now) for o in saved[:10]],
    )


# --------------------------------------------------------------------------
# Ko'rish
# --------------------------------------------------------------------------
@offers_router.get("", summary="Yig'ilgan narxlar")
async def get_offers(
    country: Optional[str] = None,
    city: Optional[str] = None,
    board: Optional[str] = None,
    star: Optional[str] = None,
    nights: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    only_fresh: bool = True,
    saved_only: bool = False,
    limit: int = 100,
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
) -> list[OfferOut]:
    """Filtrlangan takliflar, agentning foydasi bo'yicha tartiblangan."""
    cid = _company_id(current_user)
    rows = await list_offers(
        db,
        company_id=cid,
        country=country,
        city=city,
        board=board,
        star=star,
        nights=nights,
        price_min=price_min,
        price_max=price_max,
        only_fresh=only_fresh,
        saved_only=saved_only,
        limit=limit,
    )
    now = datetime.now(rows[0].fetched_at.tzinfo) if rows else datetime.now()
    return [_offer_out(o, now) for o in rows]


@offers_router.post("/{offer_id}/save", summary="Taklifni saqlab qo'yish")
async def save_offer(
    offer_id: int,
    current_user: User = Depends(_STAFF),
    db: AsyncSession = Depends(get_db),
) -> OfferOut:
    """Taklifni doimiy qiladi — muddati o'tsa ham ro'yxatda qoladi."""
    cid = _company_id(current_user)
    offer = (
        await db.execute(
            select(TourOffer).where(
                TourOffer.id == offer_id, TourOffer.company_id == cid
            )
        )
    ).scalar_one_or_none()
    if offer is None:
        raise HTTPException(status_code=404, detail="Taklif topilmadi")

    offer.is_saved = True
    await db.flush()
    return _offer_out(offer, datetime.now(offer.fetched_at.tzinfo))
