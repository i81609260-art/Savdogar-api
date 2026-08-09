"""Brauzer kengaytmasi: kalitlar va narx qabul qilish.

Kengaytma turagentning O'Z brauzerida ishlaydi. Sabab amaliy: serverdagi
brauzer operator saytlariga kira olmaydi — ma'lumot markazi IP'si
bloklanadi (Cloudflare 520, timeout — haqiqiy saytlarda sinaldi).
Agentning brauzeri esa mahalliy IP va haqiqiy seans bilan ishlaydi.

Kengaytma sahifaning MATNINI yuboradi, tayyor jadval emas. Sabab: operator
saytlari har xil va har biriga selektor yozish cheksiz ish bo'lardi. Bizda
esa allaqachon ishlaydigan matn tahlilchisi bor (`pricelist_parser`) — u
Telegram xabarini ham, jadvalni ham o'qiydi. Kengaytmaning vazifasi
shunchaki matnni agentning brauzeridan serverga olib o'tish.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.extension_key import ExtensionKey
from app.models.tour_offer import OfferSource
from app.models.tour_operator import TourOperator
from app.models.user import User, UserRole
from app.services.offer_service import save_offers
from app.services.pricelist_parser import parse_text
from app.utils.security import hash_password, verify_password

router = APIRouter(prefix="/api/extension", tags=["Brauzer kengaytmasi"])

# Prefiks kalitni ko'rganda nima ekanini bildiradi. Bu GitHub va Stripe
# qo'llaydigan usul: tasodifan kodga yopishtirilgan kalitni qidiruv bilan
# topish oson bo'ladi.
KEY_PREFIX = "trf_"
PREFIX_SHOWN = 12          # ro'yxatda ko'rsatiladigan qism
MAX_PAGE_CHARS = 200_000   # bitta sahifa matni uchun oqilona chegara


# --------------------------------------------------------------------------
# Kalitlarni boshqarish (oddiy JWT bilan, paneldan)
# --------------------------------------------------------------------------
class KeyOut(BaseModel):
    id: int
    label: Optional[str]
    key_prefix: str
    is_active: bool
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]


class KeyCreated(KeyOut):
    """Ochiq kalit FAQAT shu javobda bo'ladi va boshqa qaytarilmaydi."""

    key: str


class KeyIn(BaseModel):
    label: Optional[str] = Field(default=None, max_length=100)


def _staff(user: User) -> int:
    if user.role not in (UserRole.ADMIN, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")
    return user.company_id


def _out(k: ExtensionKey) -> KeyOut:
    return KeyOut(
        id=k.id,
        label=k.label,
        key_prefix=k.key_prefix,
        is_active=k.is_active,
        created_at=k.created_at,
        last_used_at=k.last_used_at,
    )


@router.get("/keys", summary="Kengaytma kalitlari")
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KeyOut]:
    cid = _staff(current_user)
    rows = (
        await db.execute(
            select(ExtensionKey)
            .where(ExtensionKey.company_id == cid)
            .order_by(ExtensionKey.id.desc())
        )
    ).scalars().all()
    return [_out(k) for k in rows]


@router.post("/keys", status_code=201, summary="Yangi kalit yaratish")
async def create_key(
    payload: KeyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyCreated:
    """Kalit yaratadi va ochiq qiymatini BIR MARTA qaytaradi."""
    cid = _staff(current_user)

    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    key = ExtensionKey(
        company_id=cid,
        user_id=current_user.id,
        key_hash=hash_password(raw),
        key_prefix=raw[:PREFIX_SHOWN],
        label=payload.label,
    )
    db.add(key)
    await db.flush()
    await db.refresh(key)

    return KeyCreated(**_out(key).model_dump(), key=raw)


@router.delete("/keys/{key_id}", summary="Kalitni bekor qilish")
async def revoke_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyOut:
    """Kalitni bekor qiladi. Yozuv O'CHIRILMAYDI — tarix saqlanadi."""
    cid = _staff(current_user)
    key = (
        await db.execute(
            select(ExtensionKey).where(
                ExtensionKey.id == key_id, ExtensionKey.company_id == cid
            )
        )
    ).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="Kalit topilmadi")

    key.is_active = False
    await db.flush()
    return _out(key)


# --------------------------------------------------------------------------
# Kengaytmadan narx qabul qilish (API kalit bilan)
# --------------------------------------------------------------------------
async def _company_from_key(
    db: AsyncSession, api_key: Optional[str]
) -> ExtensionKey:
    """`X-API-Key` sarlavhasidan firmani aniqlaydi.

    Xesh solishtirish sekin (bcrypt), shuning uchun avval PREFIKS bo'yicha
    tanlab olamiz — aks holda har so'rovda barcha kalitlarni tekshirishga
    to'g'ri kelardi.
    """
    if not api_key or not api_key.startswith(KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Kalit noto'g'ri")

    rows = (
        await db.execute(
            select(ExtensionKey).where(
                ExtensionKey.key_prefix == api_key[:PREFIX_SHOWN],
                ExtensionKey.is_active == True,  # noqa: E712
            )
        )
    ).scalars().all()

    for key in rows:
        if verify_password(api_key, key.key_hash):
            key.last_used_at = datetime.now(timezone.utc)
            return key

    raise HTTPException(status_code=401, detail="Kalit noto'g'ri")


class PageIn(BaseModel):
    """Kengaytma yuborgan sahifa."""

    text: str = Field(min_length=1, max_length=MAX_PAGE_CHARS)
    url: Optional[str] = Field(default=None, max_length=500)
    operator_name: Optional[str] = Field(default=None, max_length=200)


class IngestResult(BaseModel):
    saved: int
    total_rows: int
    skipped: int
    warnings: list[str]
    operator_id: Optional[int]


@router.post("/pricelist", summary="Kengaytmadan narx qabul qilish")
async def ingest_pricelist(
    payload: PageIn,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> IngestResult:
    """Operator kabinetidagi sahifa matnidan takliflarni ajratib saqlaydi."""
    key = await _company_from_key(db, x_api_key)
    cid = key.company_id

    result = parse_text(payload.text)

    # Operatorni nomi bo'yicha topamiz. Topilmasa ham saqlaymiz: narx
    # operatorsiz ham foydali, aks holda agent avval operator qo'shmaguncha
    # kengaytma umuman ishlamasdi.
    operator_id: Optional[int] = None
    if payload.operator_name:
        operator = (
            await db.execute(
                select(TourOperator).where(
                    TourOperator.name.ilike(payload.operator_name.strip()),
                    TourOperator.company_id.in_([cid, None]),
                )
            )
        ).scalars().first()
        operator_id = operator.id if operator else None

    saved = await save_offers(
        db,
        company_id=cid,
        offers=result.offers,
        source=OfferSource.EXTENSION,
        operator_id=operator_id,
    )

    return IngestResult(
        saved=len(saved),
        total_rows=result.total_rows,
        skipped=result.skipped,
        warnings=result.warnings[:10],
        operator_id=operator_id,
    )
