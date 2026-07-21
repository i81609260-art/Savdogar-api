"""Subscription plan (tariff) API — view current plan, switch, and audit log."""

import asyncio
import json
import logging
from typing import Any, Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.middleware.auth import get_current_user
from app.middleware.role_guard import role_required
from app.models.company import Company
from app.models.tariff_change import TariffChange
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.services.tariff import DEFAULT_TARIFF, TARIFFS, get_tariff, tariff_list

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/tariff", tags=["Tariff"])


class SwitchRequest(BaseModel):
    tariff: str


async def _apply_tariff(db: AsyncSession, company: Company, new_tariff: str) -> bool:
    """Kompaniya tarifini o'zgartirib, o'zgarishni jurnalga yozadi.

    Local switch ham, Stripe to'lovi ham shu yagona nuqtadan o'tadi.
    """
    old_tariff = getattr(company, "tariff", DEFAULT_TARIFF)
    if old_tariff == new_tariff:
        return False
    company.tariff = new_tariff
    db.add(company)
    db.add(
        TariffChange(
            company_id=company.id,
            company_name=company.name,
            from_tariff=old_tariff,
            to_tariff=new_tariff,
        )
    )
    await db.commit()
    return True


@router.get("/plans", summary="Barcha tariflar")
async def get_plans() -> dict:
    """All subscription plans, cheapest first."""
    return {"plans": tariff_list()}


@router.get("/current", summary="Joriy tarif va limitlar")
async def get_current(
    current_user: User = Depends(role_required(UserRole.ADMIN, UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The company's active plan plus current usage against its limits."""
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    company = (
        await db.execute(select(Company).where(Company.id == current_user.company_id))
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    tariff = get_tariff(getattr(company, "tariff", DEFAULT_TARIFF))
    tours_used = (
        await db.execute(
            select(func.count(Tour.id)).where(Tour.company_id == company.id)
        )
    ).scalar() or 0
    operators_used = (
        await db.execute(
            select(func.count(User.id)).where(
                User.company_id == company.id,
                User.role.in_([UserRole.ADMIN, UserRole.OPERATOR]),
            )
        )
    ).scalar() or 0

    return {
        "tariff": tariff,
        "usage": {"tours": tours_used, "operators": operators_used},
    }


@router.post("/switch", summary="Boshqa tarifga o'tish")
async def switch_tariff(
    data: SwitchRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Switch the company's plan. The new limits take effect immediately in the
    DB; the client should sign the user out so a fresh login picks them up."""
    if data.tariff not in TARIFFS:
        raise HTTPException(status_code=400, detail="Noma'lum tarif")
    # Maxsus rejalarni (masalan "cheksiz") admin o'ziga o'zi bera olmaydi.
    if not get_tariff(data.tariff).get("purchasable", True):
        raise HTTPException(status_code=403, detail="Bu reja tanlanmaydi")
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    company = (
        await db.execute(select(Company).where(Company.id == current_user.company_id))
    ).scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")

    changed = await _apply_tariff(db, company, data.tariff)
    return {"tariff": get_tariff(data.tariff), "changed": changed}


# ---------------------------------------------------------------------------
# Stripe — xalqaro obuna to'lovi (Visa/Mastercard)
# ---------------------------------------------------------------------------


@router.get("/payment-config", summary="To'lov sozlamalari")
async def payment_config() -> dict:
    """Frontend Stripe tugmasini ko'rsatishi kerakmi."""
    return {"stripe_enabled": bool(settings.stripe_secret_key)}


@router.post("/checkout", summary="Stripe orqali tarifni sotib olish")
async def create_checkout(
    data: SwitchRequest,
    current_user: User = Depends(role_required(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tanlangan tarif uchun Stripe Checkout sessiyasini yaratadi.

    Tarif shu yerda o'zgarmaydi — u faqat webhook to'lov tasdiqlangach yoqiladi.
    """
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=400, detail="Stripe sozlanmagan")
    if data.tariff not in TARIFFS:
        raise HTTPException(status_code=400, detail="Noma'lum tarif")
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyaga biriktirilmagansiz")

    plan = get_tariff(data.tariff)
    price_usd = plan.get("price_usd")
    if not price_usd:
        raise HTTPException(status_code=400, detail="Bu tarif kartada mavjud emas")

    stripe.api_key = settings.stripe_secret_key
    base = settings.frontend_url.rstrip("/")
    try:
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="subscription",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"Turify — {plan['name']}"},
                        # Dollar narxini tiyinga (cent) aylantiramiz — kasrni saqlaydi.
                        "unit_amount": round(float(price_usd) * 100),
                        "recurring": {"interval": "month"},
                    },
                    "quantity": 1,
                }
            ],
            client_reference_id=str(current_user.company_id),
            metadata={"company_id": str(current_user.company_id), "tariff": data.tariff},
            success_url=f"{base}/admin/tariff?paid=1",
            cancel_url=f"{base}/admin/tariff?canceled=1",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stripe checkout yaratilmadi")
        raise HTTPException(status_code=502, detail="To'lov sahifasi yaratilmadi") from exc

    return {"url": session.url}


@router.post("/stripe/webhook", summary="Stripe webhook (ichki)")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """To'lov tasdiqlangach tarifni yoqadi. Stripe imzosi tekshiriladi."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=400, detail="Webhook sozlanmagan")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except Exception as exc:  # noqa: BLE001 — imzo yaroqsiz yoki payload buzilgan
        logger.warning("Stripe webhook imzosi yaroqsiz: %s", exc)
        raise HTTPException(status_code=400, detail="Yaroqsiz imzo") from exc

    # İmzo tasdiqlandi — endi xom payload'ni oddiy dict sifatida o'qiymiz
    # (Stripe obyektlari .get()ni qo'llab-quvvatlamaydi).
    event = json.loads(payload)

    if event.get("type") == "checkout.session.completed":
        obj = event.get("data", {}).get("object", {})
        meta = obj.get("metadata") or {}
        company_id = meta.get("company_id") or obj.get("client_reference_id")
        tariff = meta.get("tariff")
        if company_id and tariff in TARIFFS:
            company = (
                await db.execute(select(Company).where(Company.id == int(company_id)))
            ).scalar_one_or_none()
            if company:
                await _apply_tariff(db, company, tariff)
                logger.info("Stripe: kompaniya %s -> %s tarif", company_id, tariff)

    return {"received": True}


@router.get("/changes", summary="Tarif o'zgarishlari (superadmin)")
async def list_changes(
    current_user: User = Depends(role_required(UserRole.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recent plan switches — which company moved to which plan."""
    rows = (
        await db.execute(
            select(TariffChange).order_by(TariffChange.created_at.desc()).limit(100)
        )
    ).scalars().all()
    return {
        "changes": [
            {
                "id": r.id,
                "company_id": r.company_id,
                "company_name": r.company_name,
                "from_tariff": r.from_tariff,
                "from_name": get_tariff(r.from_tariff)["name"] if r.from_tariff else None,
                "to_tariff": r.to_tariff,
                "to_name": get_tariff(r.to_tariff)["name"],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
